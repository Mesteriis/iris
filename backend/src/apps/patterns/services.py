from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.apps.cross_market.models import Sector, SectorMetric
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.domain import ensure_utc
from src.apps.market_data.models import Candle, Coin
from src.apps.market_data.repos import CandlePoint
from src.apps.patterns.domain.clusters import build_pattern_clusters
from src.apps.patterns.domain.context import enrich_signal_context, refresh_recent_signal_contexts
from src.apps.patterns.domain.cycle import refresh_market_cycles, update_market_cycle
from src.apps.patterns.domain.decision import evaluate_investment_decision, refresh_investment_decisions
from src.apps.patterns.domain.discovery import refresh_discovered_patterns
from src.apps.patterns.domain.engine import PatternEngine
from src.apps.patterns.domain.evaluation import run_pattern_evaluation_cycle
from src.apps.patterns.domain.hierarchy import build_hierarchy_signals
from src.apps.patterns.domain.lifecycle import PatternLifecycleState
from src.apps.patterns.domain.narrative import SectorNarrative, build_sector_narratives, refresh_sector_metrics
from src.apps.patterns.domain.regime import RegimeRead, compute_live_regimes, detect_market_regime, read_regime_details
from src.apps.patterns.domain.registry import feature_enabled, sync_pattern_metadata
from src.apps.patterns.domain.success import apply_pattern_success_validation, load_pattern_success_snapshot
from src.apps.patterns.domain.strategy import refresh_strategies
from src.apps.patterns.domain.utils import current_indicator_map
from src.apps.patterns.models import DiscoveredPattern, MarketCycle, PatternFeature, PatternRegistry, PatternStatistic
from src.apps.patterns.selectors import (
    _signal_select,
    get_coin_regimes,
    list_coin_patterns,
    list_discovered_patterns,
    list_market_cycles,
    list_pattern_features,
    list_patterns,
    list_sector_metrics,
    list_sectors,
    update_pattern,
    update_pattern_feature,
)
from src.apps.signals.models import Signal


def _serialize_pattern_statistics(stats: Sequence[PatternStatistic]) -> dict[str, list[dict[str, Any]]]:
    stats_by_slug: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stat in stats:
        stats_by_slug[stat.pattern_slug].append(
            {
                "timeframe": stat.timeframe,
                "market_regime": stat.market_regime,
                "sample_size": stat.sample_size,
                "total_signals": stat.total_signals,
                "successful_signals": stat.successful_signals,
                "success_rate": stat.success_rate,
                "avg_return": stat.avg_return,
                "avg_drawdown": stat.avg_drawdown,
                "temperature": stat.temperature,
                "enabled": stat.enabled,
                "last_evaluated_at": stat.last_evaluated_at,
                "updated_at": stat.updated_at,
            }
        )
    return stats_by_slug


async def _fetch_candle_points_async(
    db: AsyncSession,
    *,
    coin_id: int,
    timeframe: int,
    limit: int,
) -> list[CandlePoint]:
    rows = (
        await db.execute(
            select(Candle.timestamp, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume)
            .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(max(limit, 1))
        )
    ).all()
    return [
        CandlePoint(
            timestamp=ensure_utc(row.timestamp),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume) if row.volume is not None else None,
        )
        for row in reversed(rows)
    ]


async def _compute_live_regimes_async(db: AsyncSession, coin_id: int) -> list[RegimeRead]:
    items: list[RegimeRead] = []
    for timeframe in (15, 60, 240, 1440):
        candles = await _fetch_candle_points_async(db, coin_id=coin_id, timeframe=timeframe, limit=200)
        if len(candles) < 20:
            continue
        indicators = current_indicator_map(candles)
        regime, confidence = detect_market_regime(indicators)
        items.append(RegimeRead(timeframe=timeframe, regime=regime, confidence=confidence))
    return items


async def _cluster_membership_map_async(
    db: AsyncSession,
    rows: Sequence[object],
) -> dict[tuple[int, int, object], list[str]]:
    if not rows:
        return {}
    coin_ids = sorted({int(row.coin_id) for row in rows})
    timeframes = sorted({int(row.timeframe) for row in rows})
    timestamps = sorted({row.candle_timestamp for row in rows})
    cluster_rows = (
        await db.execute(
            select(Signal.coin_id, Signal.timeframe, Signal.candle_timestamp, Signal.signal_type).where(
                Signal.coin_id.in_(coin_ids),
                Signal.timeframe.in_(timeframes),
                Signal.candle_timestamp.in_(timestamps),
                Signal.signal_type.like("pattern_cluster_%"),
            )
        )
    ).all()
    membership: dict[tuple[int, int, object], list[str]] = defaultdict(list)
    for row in cluster_rows:
        membership[(int(row.coin_id), int(row.timeframe), row.candle_timestamp)].append(str(row.signal_type))
    return membership


async def _serialize_signal_rows_async(
    db: AsyncSession,
    rows: Sequence[object],
) -> list[dict[str, Any]]:
    membership = await _cluster_membership_map_async(db, rows)
    payload: list[dict[str, Any]] = []
    for row in rows:
        regime_snapshot = read_regime_details(row.market_regime_details, int(row.timeframe))
        payload.append(
            {
                "id": int(row.id),
                "coin_id": int(row.coin_id),
                "symbol": str(row.symbol),
                "name": str(row.name),
                "sector": row.sector,
                "timeframe": int(row.timeframe),
                "signal_type": str(row.signal_type),
                "confidence": float(row.confidence),
                "priority_score": float(row.priority_score or 0.0),
                "context_score": float(row.context_score or 0.0),
                "regime_alignment": float(row.regime_alignment or 0.0),
                "candle_timestamp": row.candle_timestamp,
                "created_at": row.created_at,
                "market_regime": row.signal_market_regime
                or (regime_snapshot.regime if regime_snapshot is not None else row.market_regime),
                "cycle_phase": row.cycle_phase,
                "cycle_confidence": float(row.cycle_confidence) if row.cycle_confidence is not None else None,
                "cluster_membership": membership.get((int(row.coin_id), int(row.timeframe), row.candle_timestamp), []),
            }
        )
    return payload


async def _coin_bar_return_async(
    db: AsyncSession,
    *,
    coin_id: int,
    timeframe: int,
) -> tuple[float | None, float | None]:
    candles = await _fetch_candle_points_async(db, coin_id=coin_id, timeframe=timeframe, limit=25)
    if len(candles) < 2:
        return None, None
    previous = float(candles[-2].close)
    current = float(candles[-1].close)
    change = (current - previous) / previous if previous else 0.0
    closes = [float(item.close) for item in candles[-20:]]
    mean_close = sum(closes) / len(closes)
    volatility = (sum((value - mean_close) ** 2 for value in closes) / len(closes)) ** 0.5 if closes else 0.0
    return change, (volatility / current if current else 0.0)


def _capital_wave_bucket(
    coin: Coin,
    metrics: CoinMetrics | None,
    *,
    top_sector_id: int | None,
) -> str:
    market_cap = float(metrics.market_cap or 0.0) if metrics is not None else 0.0
    if coin.symbol == "BTCUSD":
        return "btc"
    if market_cap >= 15_000_000_000:
        return "large_caps"
    if top_sector_id is not None and coin.sector_id == top_sector_id:
        return "sector_leaders"
    if market_cap >= 1_000_000_000:
        return "mid_caps"
    return "micro_caps"


async def _build_sector_narratives_async(db: AsyncSession) -> list[SectorNarrative]:
    metrics = (
        await db.execute(
            select(SectorMetric)
            .options(selectinload(SectorMetric.sector))
            .order_by(SectorMetric.timeframe.asc(), SectorMetric.relative_strength.desc())
        )
    ).scalars().all()
    by_timeframe: dict[int, list[SectorMetric]] = defaultdict(list)
    for metric in metrics:
        by_timeframe[int(metric.timeframe)].append(metric)

    btc_metrics = (
        await db.execute(
            select(CoinMetrics)
            .join(Coin, CoinMetrics.coin_id == Coin.id)
            .where(Coin.symbol == "BTCUSD")
        )
    ).scalar_one_or_none()
    market_caps = (
        await db.execute(
            select(CoinMetrics.market_cap)
            .join(Coin, CoinMetrics.coin_id == Coin.id)
            .where(Coin.asset_type == "crypto", Coin.deleted_at.is_(None))
        )
    ).scalars().all()
    total_market_cap = sum(float(value or 0.0) for value in market_caps)
    btc_dominance = (
        float(btc_metrics.market_cap or 0.0) / total_market_cap
        if btc_metrics is not None and total_market_cap > 0
        else None
    )
    crypto_coins = (
        await db.execute(
            select(Coin)
            .where(Coin.asset_type == "crypto", Coin.enabled.is_(True), Coin.deleted_at.is_(None))
            .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
        )
    ).scalars().all()
    metrics_by_coin = {}
    if crypto_coins:
        metrics_rows = (
            await db.execute(select(CoinMetrics).where(CoinMetrics.coin_id.in_([coin.id for coin in crypto_coins])))
        ).scalars().all()
        metrics_by_coin = {int(item.coin_id): item for item in metrics_rows}

    narratives: list[SectorNarrative] = []
    for timeframe, items in by_timeframe.items():
        leader = next((item for item in items if item.sector is not None), None)
        top_sector = leader.sector.name if leader is not None and leader.sector is not None else None
        top_sector_id = int(leader.sector_id) if leader is not None else None
        if btc_dominance is None:
            rotation_state = None
        elif btc_dominance >= 0.45 and (btc_metrics.price_change_24h or 0.0) >= 0:
            rotation_state = "btc_dominance_rising"
        elif btc_dominance < 0.45 and (btc_metrics.price_change_24h or 0.0) < 0:
            rotation_state = "btc_dominance_falling"
        else:
            rotation_state = "sector_leadership_change" if top_sector is not None else None
        bucket_scores: dict[str, list[float]] = defaultdict(list)
        for coin in crypto_coins:
            metrics_row = metrics_by_coin.get(int(coin.id))
            price_change, _ = await _coin_bar_return_async(db, coin_id=int(coin.id), timeframe=timeframe)
            if price_change is None:
                continue
            bucket = _capital_wave_bucket(coin, metrics_row, top_sector_id=top_sector_id)
            market_cap_weight = (
                min(float(metrics_row.market_cap or 0.0) / 25_000_000_000, 2.0)
                if metrics_row is not None
                else 0.0
            )
            volume_flow = float(metrics_row.volume_change_24h or 0.0) / 100 if metrics_row is not None else 0.0
            bucket_scores[bucket].append(price_change + volume_flow + (market_cap_weight * price_change))
        capital_wave = None
        if bucket_scores:
            capital_wave = max(
                ("btc", "large_caps", "sector_leaders", "mid_caps", "micro_caps"),
                key=lambda bucket: sum(bucket_scores.get(bucket, [])) / len(bucket_scores.get(bucket, [1e-9])),
            )
        narratives.append(
            SectorNarrative(
                timeframe=timeframe,
                top_sector=top_sector,
                rotation_state=rotation_state,
                btc_dominance=btc_dominance,
                capital_wave=capital_wave,
            )
        )
    return narratives


async def list_patterns_async(db: AsyncSession):
    rows = (
        await db.execute(select(PatternRegistry).order_by(PatternRegistry.category.asc(), PatternRegistry.slug.asc()))
    ).scalars().all()
    stats = (
        await db.execute(select(PatternStatistic).order_by(PatternStatistic.pattern_slug.asc(), PatternStatistic.timeframe.asc()))
    ).scalars().all()
    stats_by_slug = _serialize_pattern_statistics(stats)
    return [
        {
            "slug": row.slug,
            "category": row.category,
            "enabled": row.enabled,
            "cpu_cost": row.cpu_cost,
            "lifecycle_state": row.lifecycle_state,
            "created_at": row.created_at,
            "statistics": stats_by_slug.get(row.slug, []),
        }
        for row in rows
    ]


async def list_pattern_features_async(db: AsyncSession):
    rows = (await db.execute(select(PatternFeature).order_by(PatternFeature.feature_slug.asc()))).scalars().all()
    return [
        {
            "feature_slug": row.feature_slug,
            "enabled": row.enabled,
            "created_at": row.created_at,
        }
        for row in rows
    ]


async def update_pattern_feature_async(db: AsyncSession, feature_slug: str, *, enabled: bool):
    row = await db.get(PatternFeature, feature_slug)
    if row is None:
        return None
    row.enabled = enabled
    await db.commit()
    await db.refresh(row)
    return {
        "feature_slug": row.feature_slug,
        "enabled": row.enabled,
        "created_at": row.created_at,
    }


async def update_pattern_async(
    db: AsyncSession,
    slug: str,
    *,
    enabled,
    lifecycle_state,
    cpu_cost,
):
    row = await db.get(PatternRegistry, slug)
    if row is None:
        return None
    if enabled is not None:
        row.enabled = enabled
        if not enabled:
            row.lifecycle_state = PatternLifecycleState.DISABLED.value
    if lifecycle_state is not None:
        normalized_state = lifecycle_state.strip().upper()
        if normalized_state not in {item.value for item in PatternLifecycleState}:
            raise ValueError(f"Unsupported lifecycle state '{lifecycle_state}'.")
        row.lifecycle_state = normalized_state
    if cpu_cost is not None:
        row.cpu_cost = max(cpu_cost, 1)
    await db.commit()
    await db.refresh(row)

    stats = (
        await db.execute(
            select(PatternStatistic)
            .where(PatternStatistic.pattern_slug == slug)
            .order_by(PatternStatistic.timeframe.asc())
        )
    ).scalars().all()
    return {
        "slug": row.slug,
        "category": row.category,
        "enabled": row.enabled,
        "cpu_cost": row.cpu_cost,
        "lifecycle_state": row.lifecycle_state,
        "created_at": row.created_at,
        "statistics": _serialize_pattern_statistics(stats).get(row.slug, []),
    }


async def list_discovered_patterns_async(
    db: AsyncSession,
    *,
    timeframe: int | None = None,
    limit: int = 200,
):
    stmt = (
        select(DiscoveredPattern)
        .order_by(DiscoveredPattern.confidence.desc(), DiscoveredPattern.sample_size.desc())
        .limit(max(limit, 1))
    )
    if timeframe is not None:
        stmt = stmt.where(DiscoveredPattern.timeframe == timeframe)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "structure_hash": row.structure_hash,
            "timeframe": row.timeframe,
            "sample_size": row.sample_size,
            "avg_return": row.avg_return,
            "avg_drawdown": row.avg_drawdown,
            "confidence": row.confidence,
        }
        for row in rows
    ]


async def list_coin_patterns_async(db: AsyncSession, symbol: str, *, limit: int = 200):
    rows = (
        await db.execute(
            _signal_select()
            .where(Coin.symbol == symbol.upper(), Signal.signal_type.like("pattern_%"))
            .order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc())
            .limit(max(limit, 1))
        )
    ).all()
    return await _serialize_signal_rows_async(db, rows)


async def get_coin_regimes_async(db: AsyncSession, symbol: str):
    coin = (
        await db.execute(
            select(Coin).where(Coin.symbol == symbol.upper(), Coin.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if coin is None:
        return None
    metrics = (
        await db.execute(select(CoinMetrics).where(CoinMetrics.coin_id == coin.id))
    ).scalar_one_or_none()
    regime_enabled = bool(
        (
            await db.execute(
                select(PatternFeature.enabled).where(PatternFeature.feature_slug == "market_regime_engine")
            )
        ).scalar_one_or_none()
    )
    items: list[RegimeRead]
    if not regime_enabled:
        items = []
    elif metrics is not None and metrics.market_regime_details:
        items = [
            item
            for timeframe in (15, 60, 240, 1440)
            if (item := read_regime_details(metrics.market_regime_details, timeframe)) is not None
        ]
    else:
        items = await _compute_live_regimes_async(db, int(coin.id))
    return {
        "coin_id": coin.id,
        "symbol": coin.symbol,
        "canonical_regime": metrics.market_regime if metrics is not None and regime_enabled else None,
        "items": [
            {
                "timeframe": item.timeframe,
                "regime": item.regime,
                "confidence": item.confidence,
            }
            for item in items
        ],
    }


async def list_sectors_async(db: AsyncSession):
    rows = (
        await db.execute(
            select(
                Sector.id,
                Sector.name,
                Sector.description,
                Sector.created_at,
                func.count(Coin.id).label("coin_count"),
            )
            .outerjoin(Coin, and_(Coin.sector_id == Sector.id, Coin.deleted_at.is_(None), Coin.enabled.is_(True)))
            .group_by(Sector.id)
            .order_by(Sector.name.asc())
        )
    ).all()
    return [dict(row._mapping) for row in rows]


async def list_sector_metrics_async(db: AsyncSession, *, timeframe: int | None = None):
    stmt = (
        select(
            SectorMetric.sector_id,
            Sector.name,
            Sector.description,
            SectorMetric.timeframe,
            SectorMetric.sector_strength,
            SectorMetric.relative_strength,
            SectorMetric.capital_flow,
            SectorMetric.avg_price_change_24h,
            SectorMetric.avg_volume_change_24h,
            SectorMetric.volatility,
            SectorMetric.trend,
            SectorMetric.updated_at,
        )
        .join(Sector, Sector.id == SectorMetric.sector_id)
        .order_by(SectorMetric.timeframe.asc(), SectorMetric.relative_strength.desc())
    )
    if timeframe is not None:
        stmt = stmt.where(SectorMetric.timeframe == timeframe)
    rows = (await db.execute(stmt)).all()
    narratives = await _build_sector_narratives_async(db)
    return {
        "items": [dict(row._mapping) for row in rows],
        "narratives": [
            {
                "timeframe": item.timeframe,
                "top_sector": item.top_sector,
                "rotation_state": item.rotation_state,
                "btc_dominance": item.btc_dominance,
                "capital_wave": item.capital_wave,
            }
            for item in narratives
            if timeframe is None or item.timeframe == timeframe
        ],
    }


async def list_market_cycles_async(
    db: AsyncSession,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
):
    stmt = (
        select(
            MarketCycle.coin_id,
            Coin.symbol,
            Coin.name,
            MarketCycle.timeframe,
            MarketCycle.cycle_phase,
            MarketCycle.confidence,
            MarketCycle.detected_at,
        )
        .join(Coin, Coin.id == MarketCycle.coin_id)
        .where(Coin.deleted_at.is_(None))
        .order_by(MarketCycle.confidence.desc(), Coin.sort_order.asc(), Coin.symbol.asc())
    )
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    if timeframe is not None:
        stmt = stmt.where(MarketCycle.timeframe == timeframe)
    rows = (await db.execute(stmt)).all()
    return [dict(row._mapping) for row in rows]


__all__ = [
    "PatternEngine",
    "apply_pattern_success_validation",
    "build_hierarchy_signals",
    "build_pattern_clusters",
    "build_sector_narratives",
    "compute_live_regimes",
    "detect_market_regime",
    "enrich_signal_context",
    "evaluate_investment_decision",
    "feature_enabled",
    "get_coin_regimes",
    "get_coin_regimes_async",
    "list_coin_patterns",
    "list_coin_patterns_async",
    "list_discovered_patterns",
    "list_discovered_patterns_async",
    "list_market_cycles",
    "list_market_cycles_async",
    "list_pattern_features",
    "list_pattern_features_async",
    "list_patterns",
    "list_patterns_async",
    "list_sector_metrics",
    "list_sector_metrics_async",
    "list_sectors",
    "list_sectors_async",
    "load_pattern_success_snapshot",
    "read_regime_details",
    "refresh_discovered_patterns",
    "refresh_investment_decisions",
    "refresh_market_cycles",
    "refresh_recent_signal_contexts",
    "refresh_sector_metrics",
    "refresh_strategies",
    "run_pattern_evaluation_cycle",
    "sync_pattern_metadata",
    "update_market_cycle",
    "update_pattern",
    "update_pattern_async",
    "update_pattern_feature",
    "update_pattern_feature_async",
]
