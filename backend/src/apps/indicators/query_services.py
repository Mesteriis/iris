from __future__ import annotations

import json
from datetime import datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.apps.cross_market.models import CoinRelation, Sector, SectorMetric
from src.apps.indicators.models import CoinMetrics
from src.apps.indicators.read_models import (
    CoinMetricsReadModel,
    CoinRelationReadModel,
    MarketFlowReadModel,
    MarketLeaderReadModel,
    MarketRadarCoinReadModel,
    MarketRadarReadModel,
    MarketRegimeChangeReadModel,
    SectorMomentumReadModel,
    SectorRotationReadModel,
    SignalSummaryReadModel,
    coin_metrics_read_model_from_mapping,
    coin_relation_read_model_from_mapping,
    market_radar_coin_read_model_from_mapping,
    sector_momentum_read_model_from_mapping,
    signal_summary_read_model_from_mapping,
)
from src.apps.market_data.domain import ensure_utc
from src.apps.market_data.models import Coin
from src.apps.signals.models import Signal
from src.core.db.persistence import AsyncQueryService
from src.core.settings import get_settings


def _stream_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


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


class IndicatorQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="indicators", service_name="IndicatorQueryService")

    async def list_coin_metrics(self) -> tuple[CoinMetricsReadModel, ...]:
        self._log_debug("query.list_indicator_coin_metrics", mode="read", loading_profile="full")
        rows = (
            await self.session.execute(
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
        items = tuple(coin_metrics_read_model_from_mapping(row._mapping) for row in rows)
        self._log_debug("query.list_indicator_coin_metrics.result", mode="read", count=len(items))
        return items

    async def list_signals(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        limit: int = 100,
    ) -> tuple[SignalSummaryReadModel, ...]:
        normalized_symbol = symbol.upper() if symbol is not None else None
        self._log_debug(
            "query.list_indicator_signals",
            mode="read",
            symbol=normalized_symbol,
            timeframe=timeframe,
            limit=limit,
        )
        stmt = (
            select(
                Signal.coin_id,
                Coin.symbol,
                Coin.name,
                Signal.timeframe,
                Signal.signal_type,
                Signal.confidence,
                Signal.candle_timestamp,
                Signal.created_at,
            )
            .join(Coin, Coin.id == Signal.coin_id)
            .where(Coin.deleted_at.is_(None))
            .order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc())
            .limit(max(limit, 1))
        )
        if normalized_symbol is not None:
            stmt = stmt.where(Coin.symbol == normalized_symbol)
        if timeframe is not None:
            stmt = stmt.where(Signal.timeframe == timeframe)
        rows = (await self.session.execute(stmt)).all()
        items = tuple(signal_summary_read_model_from_mapping(row._mapping) for row in rows)
        self._log_debug("query.list_indicator_signals.result", mode="read", count=len(items))
        return items

    async def list_recent_regime_changes(self, *, limit: int) -> tuple[MarketRegimeChangeReadModel, ...]:
        self._log_debug("query.list_recent_indicator_regime_changes", mode="read", limit=limit, cacheable=True)
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
            if '"regime"' in payload:
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
            return ()

        coin_ids = sorted({coin_id for coin_id, _, _, _, _ in changes})
        coin_rows = (
            await self.session.execute(select(Coin.id, Coin.symbol, Coin.name).where(Coin.id.in_(coin_ids)))
        ).all()
        coin_map = {int(row.id): (str(row.symbol), str(row.name)) for row in coin_rows}
        items = tuple(
            MarketRegimeChangeReadModel(
                coin_id=coin_id,
                symbol=coin_map.get(coin_id, ("UNKNOWN", "Unknown"))[0],
                name=coin_map.get(coin_id, ("UNKNOWN", "Unknown"))[1],
                timeframe=timeframe,
                regime=regime,
                confidence=confidence,
                timestamp=timestamp,
            )
            for coin_id, timeframe, regime, confidence, timestamp in changes
        )
        self._log_debug("query.list_recent_indicator_regime_changes.result", mode="read", count=len(items))
        return items

    async def list_recent_market_leaders(self, *, limit: int) -> tuple[MarketLeaderReadModel, ...]:
        self._log_debug("query.list_recent_indicator_market_leaders", mode="read", limit=limit, cacheable=True)
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

        if not leaders:
            return ()

        coin_ids = [coin_id for coin_id, _, _ in leaders]
        rows = (
            await self.session.execute(
                select(
                    Coin.id,
                    Coin.symbol,
                    Coin.name,
                    Coin.sector_code,
                    CoinMetrics.market_regime,
                    CoinMetrics.price_change_24h,
                    CoinMetrics.volume_change_24h,
                )
                .outerjoin(CoinMetrics, CoinMetrics.coin_id == Coin.id)
                .where(Coin.id.in_(coin_ids))
            )
        ).all()
        coin_map = {
            int(row.id): {
                "symbol": str(row.symbol),
                "name": str(row.name),
                "sector": str(row.sector_code) if row.sector_code is not None else None,
                "regime": str(row.market_regime) if row.market_regime is not None else None,
                "price_change_24h": float(row.price_change_24h) if row.price_change_24h is not None else None,
                "volume_change_24h": float(row.volume_change_24h) if row.volume_change_24h is not None else None,
            }
            for row in rows
        }
        items = tuple(
            MarketLeaderReadModel(
                leader_coin_id=coin_id,
                symbol=coin_map[coin_id]["symbol"],
                name=coin_map[coin_id]["name"],
                sector=coin_map[coin_id]["sector"],
                regime=coin_map[coin_id]["regime"],
                confidence=confidence,
                price_change_24h=coin_map[coin_id]["price_change_24h"],
                volume_change_24h=coin_map[coin_id]["volume_change_24h"],
                timestamp=timestamp,
            )
            for coin_id, confidence, timestamp in leaders
            if coin_id in coin_map
        )
        self._log_debug("query.list_recent_indicator_market_leaders.result", mode="read", count=len(items))
        return items

    async def list_recent_sector_rotations(self, *, limit: int) -> tuple[SectorRotationReadModel, ...]:
        self._log_debug("query.list_recent_indicator_sector_rotations", mode="read", limit=limit, cacheable=True)
        settings = get_settings()
        redis = _stream_client()
        try:
            messages = await redis.xrevrange(settings.event_stream_name, "+", "-", count=max(limit * 20, 100))
        finally:
            await redis.aclose()

        rotations: list[SectorRotationReadModel] = []
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
                SectorRotationReadModel(
                    source_sector=source_sector,
                    target_sector=target_sector,
                    timeframe=timeframe,
                    timestamp=ensure_utc(datetime.fromisoformat(fields["timestamp"])),
                )
            )
            if len(rotations) >= limit:
                break
        items = tuple(rotations)
        self._log_debug("query.list_recent_indicator_sector_rotations.result", mode="read", count=len(items))
        return items

    async def get_market_radar(self, *, limit: int = 8) -> MarketRadarReadModel:
        self._log_debug("query.get_indicator_market_radar", mode="read", limit=limit, loading_profile="full")
        base_stmt = (
            select(*_metric_projection())
            .join(CoinMetrics, CoinMetrics.coin_id == Coin.id)
            .where(Coin.deleted_at.is_(None), Coin.enabled.is_(True))
        )
        hot_rows = (
            await self.session.execute(
                base_stmt.where(CoinMetrics.activity_bucket == "HOT")
                .order_by(CoinMetrics.activity_score.desc().nullslast(), Coin.symbol.asc())
                .limit(max(limit, 1))
            )
        ).all()
        emerging_rows = (
            await self.session.execute(
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
            await self.session.execute(
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
        item = MarketRadarReadModel(
            hot_coins=tuple(market_radar_coin_read_model_from_mapping(row._mapping) for row in hot_rows),
            emerging_coins=tuple(market_radar_coin_read_model_from_mapping(row._mapping) for row in emerging_rows),
            regime_changes=await self.list_recent_regime_changes(limit=max(limit, 1)),
            volatility_spikes=tuple(market_radar_coin_read_model_from_mapping(row._mapping) for row in volatility_rows),
        )
        self._log_debug(
            "query.get_indicator_market_radar.result",
            mode="read",
            hot=len(item.hot_coins),
            emerging=len(item.emerging_coins),
            regime_changes=len(item.regime_changes),
            volatility=len(item.volatility_spikes),
        )
        return item

    async def get_market_flow(self, *, limit: int = 8, timeframe: int = 60) -> MarketFlowReadModel:
        self._log_debug(
            "query.get_indicator_market_flow",
            mode="read",
            limit=limit,
            timeframe=timeframe,
            loading_profile="full",
        )
        follower_coin = aliased(Coin)
        relation_rows = (
            await self.session.execute(
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
                .order_by(
                    CoinRelation.confidence.desc(), CoinRelation.correlation.desc(), CoinRelation.updated_at.desc()
                )
                .limit(max(limit, 1))
            )
        ).all()
        sector_rows = (
            await self.session.execute(
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
        item = MarketFlowReadModel(
            leaders=await self.list_recent_market_leaders(limit=max(limit, 1)),
            relations=tuple(coin_relation_read_model_from_mapping(row._mapping) for row in relation_rows),
            sectors=tuple(sector_momentum_read_model_from_mapping(row._mapping) for row in sector_rows),
            rotations=await self.list_recent_sector_rotations(limit=max(limit, 1)),
        )
        self._log_debug(
            "query.get_indicator_market_flow.result",
            mode="read",
            leaders=len(item.leaders),
            relations=len(item.relations),
            sectors=len(item.sectors),
            rotations=len(item.rotations),
        )
        return item


__all__ = ["IndicatorQueryService"]
