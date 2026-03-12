from __future__ import annotations

import json
from datetime import datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.core.settings import get_settings
from src.apps.market_data.models import Coin
from src.apps.indicators.analytics import (
    determine_affected_timeframes,
    list_signal_types_at_timestamp,
    process_indicator_event,
)
from src.apps.indicators.domain import adx_series, atr_series, bollinger_bands, ema_series, macd_series, rsi_series, sma_series
from src.apps.indicators.models import CoinMetrics
from src.apps.indicators.schemas import CoinRelationRead, MarketFlowRead, MarketLeaderRead, MarketRadarCoinRead, MarketRadarRead, MarketRegimeChangeRead, SectorMomentumRead, SectorRotationRead
from src.apps.cross_market.models import CoinRelation, Sector, SectorMetric
from src.apps.indicators.snapshots import capture_feature_snapshot
from src.apps.market_data.domain import ensure_utc


def _stream_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def list_coin_metrics_async(db: AsyncSession):
    rows = (
        await db.execute(
            select(
                Coin.id.label("coin_id"),
                Coin.symbol,
                Coin.name,
                CoinMetrics.price_current,
                CoinMetrics.price_change_1h,
                CoinMetrics.price_change_24h,
                CoinMetrics.price_change_7d,
                CoinMetrics.ema_20,
                CoinMetrics.ema_50,
                CoinMetrics.sma_50,
                CoinMetrics.sma_200,
                CoinMetrics.rsi_14,
                CoinMetrics.macd,
                CoinMetrics.macd_signal,
                CoinMetrics.macd_histogram,
                CoinMetrics.atr_14,
                CoinMetrics.bb_upper,
                CoinMetrics.bb_middle,
                CoinMetrics.bb_lower,
                CoinMetrics.bb_width,
                CoinMetrics.adx_14,
                CoinMetrics.volume_24h,
                CoinMetrics.volume_change_24h,
                CoinMetrics.volatility,
                CoinMetrics.market_cap,
                CoinMetrics.trend,
                CoinMetrics.trend_score,
                CoinMetrics.activity_score,
                CoinMetrics.activity_bucket,
                CoinMetrics.analysis_priority,
                CoinMetrics.last_analysis_at,
                CoinMetrics.market_regime,
                CoinMetrics.market_regime_details,
                CoinMetrics.indicator_version,
                CoinMetrics.updated_at,
            )
            .join(CoinMetrics, CoinMetrics.coin_id == Coin.id)
            .where(Coin.deleted_at.is_(None))
            .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
        )
    ).all()
    return [dict(row._mapping) for row in rows]


def _metric_projection():
    return (
        Coin.id.label("coin_id"),
        Coin.symbol,
        Coin.name,
        CoinMetrics.activity_score,
        CoinMetrics.activity_bucket,
        CoinMetrics.analysis_priority,
        CoinMetrics.price_change_24h,
        CoinMetrics.price_change_7d,
        CoinMetrics.volatility,
        CoinMetrics.market_regime,
        CoinMetrics.updated_at,
        CoinMetrics.last_analysis_at,
    )


def _serialize_metric_rows(rows) -> list[MarketRadarCoinRead]:
    return [
        MarketRadarCoinRead(
            coin_id=int(row.coin_id),
            symbol=str(row.symbol),
            name=str(row.name),
            activity_score=float(row.activity_score) if row.activity_score is not None else None,
            activity_bucket=row.activity_bucket,
            analysis_priority=int(row.analysis_priority) if row.analysis_priority is not None else None,
            price_change_24h=float(row.price_change_24h) if row.price_change_24h is not None else None,
            price_change_7d=float(row.price_change_7d) if row.price_change_7d is not None else None,
            volatility=float(row.volatility) if row.volatility is not None else None,
            market_regime=row.market_regime,
            updated_at=row.updated_at,
            last_analysis_at=row.last_analysis_at,
        )
        for row in rows
    ]


async def _recent_regime_changes_async(db: AsyncSession, *, limit: int) -> list[MarketRegimeChangeRead]:
    settings = get_settings()
    redis = _stream_client()
    try:
        messages = await redis.xrevrange(settings.event_stream_name, "+", "-", count=max(limit * 40, 100))
    finally:
        await redis.aclose()

    changes: list[tuple[int, int, str, float, datetime]] = []
    seen: set[tuple[int, int, str]] = set()
    for _, fields in messages:
        if fields.get("event_type") != "market_regime_changed":
            continue
        coin_id = int(fields["coin_id"])
        timeframe = int(fields["timeframe"])
        timestamp = ensure_utc(datetime.fromisoformat(fields["timestamp"]))
        payload = fields.get("payload") or "{}"
        regime = "unknown"
        confidence = 0.0
        if "\"regime\"" in payload:
            data = json.loads(payload)
            regime = str(data.get("regime") or regime)
            confidence = float(data.get("confidence") or 0.0)
        key = (coin_id, timeframe, regime)
        if key in seen:
            continue
        seen.add(key)
        changes.append((coin_id, timeframe, regime, confidence, timestamp))
        if len(changes) >= limit:
            break

    if not changes:
        return []

    coin_ids = sorted({coin_id for coin_id, _, _, _, _ in changes})
    coin_rows = (await db.execute(select(Coin.id, Coin.symbol, Coin.name).where(Coin.id.in_(coin_ids)))).all()
    coin_map = {int(row.id): (str(row.symbol), str(row.name)) for row in coin_rows}
    return [
        MarketRegimeChangeRead(
            coin_id=coin_id,
            symbol=coin_map.get(coin_id, ("UNKNOWN", "Unknown"))[0],
            name=coin_map.get(coin_id, ("UNKNOWN", "Unknown"))[1],
            timeframe=timeframe,
            regime=regime,
            confidence=confidence,
            timestamp=timestamp,
        )
        for coin_id, timeframe, regime, confidence, timestamp in changes
    ]


async def get_market_radar_async(db: AsyncSession, *, limit: int = 8) -> MarketRadarRead:
    base_stmt = (
        select(*_metric_projection())
        .join(CoinMetrics, CoinMetrics.coin_id == Coin.id)
        .where(Coin.deleted_at.is_(None), Coin.enabled.is_(True))
    )
    hot_rows = (
        await db.execute(
            base_stmt.where(CoinMetrics.activity_bucket == "HOT")
            .order_by(CoinMetrics.activity_score.desc().nullslast(), Coin.symbol.asc())
            .limit(max(limit, 1))
        )
    ).all()
    emerging_rows = (
        await db.execute(
            base_stmt.where(
                CoinMetrics.activity_bucket.in_(("HOT", "WARM")),
                CoinMetrics.price_change_24h.is_not(None),
                CoinMetrics.price_change_24h > 0,
                CoinMetrics.price_change_7d.is_not(None),
                CoinMetrics.price_change_7d >= 0,
                CoinMetrics.market_regime.in_(("bull_trend", "sideways_range", "high_volatility")),
            )
            .order_by(
                CoinMetrics.activity_score.desc().nullslast(),
                CoinMetrics.price_change_24h.desc().nullslast(),
                Coin.symbol.asc(),
            )
            .limit(max(limit, 1))
        )
    ).all()
    volatility_rows = (
        await db.execute(
            base_stmt.where(
                CoinMetrics.volatility.is_not(None),
                CoinMetrics.activity_bucket.in_(("HOT", "WARM", "COLD")),
            )
            .order_by(
                CoinMetrics.market_regime.desc().nullslast(),
                CoinMetrics.volatility.desc().nullslast(),
                Coin.symbol.asc(),
            )
            .limit(max(limit, 1))
        )
    ).all()
    regime_changes = await _recent_regime_changes_async(db, limit=max(limit, 1))
    return MarketRadarRead(
        hot_coins=_serialize_metric_rows(hot_rows),
        emerging_coins=_serialize_metric_rows(emerging_rows),
        regime_changes=regime_changes,
        volatility_spikes=_serialize_metric_rows(volatility_rows),
    )


async def _recent_market_leaders_async(db: AsyncSession, *, limit: int) -> list[MarketLeaderRead]:
    settings = get_settings()
    redis = _stream_client()
    try:
        messages = await redis.xrevrange(settings.event_stream_name, "+", "-", count=max(limit * 30, 100))
    finally:
        await redis.aclose()

    seen: set[int] = set()
    leaders: list[tuple[int, float, datetime]] = []
    for _, fields in messages:
        if fields.get("event_type") != "market_leader_detected":
            continue
        coin_id = int(fields["coin_id"])
        if coin_id in seen:
            continue
        seen.add(coin_id)
        payload = json.loads(fields.get("payload") or "{}")
        leaders.append(
            (
                coin_id,
                float(payload.get("confidence") or 0.0),
                ensure_utc(datetime.fromisoformat(fields["timestamp"])),
            )
        )
        if len(leaders) >= limit:
            break

    result: list[MarketLeaderRead] = []
    for coin_id, confidence, timestamp in leaders:
        coin = await db.get(Coin, coin_id)
        metrics = (
            await db.execute(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
        ).scalar_one_or_none()
        if coin is None:
            continue
        result.append(
            MarketLeaderRead(
                leader_coin_id=coin_id,
                symbol=coin.symbol,
                name=coin.name,
                sector=coin.sector_code,
                regime=metrics.market_regime if metrics is not None else None,
                confidence=confidence,
                price_change_24h=float(metrics.price_change_24h) if metrics is not None and metrics.price_change_24h is not None else None,
                volume_change_24h=float(metrics.volume_change_24h) if metrics is not None and metrics.volume_change_24h is not None else None,
                timestamp=timestamp,
            )
        )
    return result


async def _recent_sector_rotations_async(*, limit: int) -> list[SectorRotationRead]:
    settings = get_settings()
    redis = _stream_client()
    try:
        messages = await redis.xrevrange(settings.event_stream_name, "+", "-", count=max(limit * 20, 100))
    finally:
        await redis.aclose()

    rotations: list[SectorRotationRead] = []
    seen: set[tuple[str, str, int]] = set()
    for _, fields in messages:
        if fields.get("event_type") != "sector_rotation_detected":
            continue
        payload = json.loads(fields.get("payload") or "{}")
        source_sector = str(payload.get("source_sector") or "")
        target_sector = str(payload.get("target_sector") or "")
        timeframe = int(fields["timeframe"])
        key = (source_sector, target_sector, timeframe)
        if not source_sector or not target_sector or key in seen:
            continue
        seen.add(key)
        rotations.append(
            SectorRotationRead(
                source_sector=source_sector,
                target_sector=target_sector,
                timeframe=timeframe,
                timestamp=ensure_utc(datetime.fromisoformat(fields["timestamp"])),
            )
        )
        if len(rotations) >= limit:
            break
    return rotations


async def get_market_flow_async(db: AsyncSession, *, limit: int = 8, timeframe: int = 60) -> MarketFlowRead:
    follower_coin = aliased(Coin)
    relation_rows = (
        await db.execute(
            select(
                CoinRelation.leader_coin_id,
                Coin.symbol.label("leader_symbol"),
                CoinRelation.follower_coin_id,
                follower_coin.symbol.label("follower_symbol"),
                CoinRelation.correlation,
                CoinRelation.lag_hours,
                CoinRelation.confidence,
                CoinRelation.updated_at,
            )
            .join(Coin, Coin.id == CoinRelation.leader_coin_id)
            .join(follower_coin, CoinRelation.follower_coin_id == follower_coin.id)
            .order_by(CoinRelation.confidence.desc(), CoinRelation.correlation.desc(), CoinRelation.updated_at.desc())
            .limit(max(limit, 1))
        )
    ).all()
    sector_rows = (
        await db.execute(
            select(
                SectorMetric.sector_id,
                Sector.name.label("sector"),
                SectorMetric.timeframe,
                SectorMetric.avg_price_change_24h,
                SectorMetric.avg_volume_change_24h,
                SectorMetric.volatility,
                SectorMetric.trend,
                SectorMetric.relative_strength,
                SectorMetric.capital_flow,
                SectorMetric.updated_at,
            )
            .join(Sector, Sector.id == SectorMetric.sector_id)
            .where(SectorMetric.timeframe == timeframe)
            .order_by(SectorMetric.relative_strength.desc(), Sector.name.asc())
            .limit(max(limit, 1))
        )
    ).all()
    return MarketFlowRead(
        leaders=await _recent_market_leaders_async(db, limit=max(limit, 1)),
        relations=[CoinRelationRead.model_validate(dict(row._mapping)) for row in relation_rows],
        sectors=[SectorMomentumRead.model_validate(dict(row._mapping)) for row in sector_rows],
        rotations=await _recent_sector_rotations_async(limit=max(limit, 1)),
    )


__all__ = [
    "adx_series",
    "atr_series",
    "bollinger_bands",
    "capture_feature_snapshot",
    "determine_affected_timeframes",
    "ema_series",
    "get_market_flow_async",
    "get_market_radar_async",
    "list_coin_metrics",
    "list_coin_metrics_async",
    "list_signal_types_at_timestamp",
    "macd_series",
    "process_indicator_event",
    "rsi_series",
    "sma_series",
]
