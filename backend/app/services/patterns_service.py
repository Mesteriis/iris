from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.coin import Coin
from app.models.coin_metrics import CoinMetrics
from app.models.market_cycle import MarketCycle
from app.models.pattern_registry import PatternRegistry
from app.models.pattern_statistic import PatternStatistic
from app.models.sector import Sector
from app.models.sector_metric import SectorMetric
from app.models.signal import Signal
from app.patterns.narrative import build_sector_narratives
from app.patterns.regime import compute_live_regimes
from app.services.history_loader import get_coin_by_symbol


def list_patterns(db: Session) -> Sequence[dict[str, Any]]:
    rows = db.scalars(select(PatternRegistry).order_by(PatternRegistry.category.asc(), PatternRegistry.slug.asc())).all()
    stats = db.scalars(
        select(PatternStatistic).order_by(PatternStatistic.pattern_slug.asc(), PatternStatistic.timeframe.asc())
    ).all()
    stats_by_slug: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stat in stats:
        stats_by_slug[stat.pattern_slug].append(
            {
                "timeframe": stat.timeframe,
                "sample_size": stat.sample_size,
                "success_rate": stat.success_rate,
                "avg_return": stat.avg_return,
                "avg_drawdown": stat.avg_drawdown,
                "temperature": stat.temperature,
                "updated_at": stat.updated_at,
            }
        )
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


def _cluster_membership_map(db: Session, rows: Sequence[object]) -> dict[tuple[int, int, object], list[str]]:
    if not rows:
        return {}
    coin_ids = sorted({int(row.coin_id) for row in rows})
    timeframes = sorted({int(row.timeframe) for row in rows})
    timestamps = sorted({row.candle_timestamp for row in rows})
    cluster_rows = db.execute(
        select(Signal.coin_id, Signal.timeframe, Signal.candle_timestamp, Signal.signal_type).where(
            Signal.coin_id.in_(coin_ids),
            Signal.timeframe.in_(timeframes),
            Signal.candle_timestamp.in_(timestamps),
            Signal.signal_type.like("pattern_cluster_%"),
        )
    ).all()
    membership: dict[tuple[int, int, object], list[str]] = defaultdict(list)
    for row in cluster_rows:
        membership[(int(row.coin_id), int(row.timeframe), row.candle_timestamp)].append(str(row.signal_type))
    return membership


def _serialize_signal_rows(db: Session, rows: Sequence[object]) -> list[dict[str, Any]]:
    membership = _cluster_membership_map(db, rows)
    return [
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
            "market_regime": row.market_regime,
            "cycle_phase": row.cycle_phase,
            "cycle_confidence": float(row.cycle_confidence) if row.cycle_confidence is not None else None,
            "cluster_membership": membership.get((int(row.coin_id), int(row.timeframe), row.candle_timestamp), []),
        }
        for row in rows
    ]


def _signal_select():
    return (
        select(
            Signal.id,
            Signal.coin_id,
            Coin.symbol,
            Coin.name,
            Sector.name.label("sector"),
            Signal.timeframe,
            Signal.signal_type,
            Signal.confidence,
            Signal.priority_score,
            Signal.context_score,
            Signal.regime_alignment,
            Signal.candle_timestamp,
            Signal.created_at,
            CoinMetrics.market_regime,
            MarketCycle.cycle_phase,
            MarketCycle.confidence.label("cycle_confidence"),
        )
        .join(Coin, Coin.id == Signal.coin_id)
        .outerjoin(Sector, Sector.id == Coin.sector_id)
        .outerjoin(CoinMetrics, CoinMetrics.coin_id == Coin.id)
        .outerjoin(
            MarketCycle,
            and_(
                MarketCycle.coin_id == Signal.coin_id,
                MarketCycle.timeframe == Signal.timeframe,
            ),
        )
        .where(Coin.deleted_at.is_(None))
    )


def list_enriched_signals(
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
) -> Sequence[dict[str, Any]]:
    stmt = _signal_select().order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc()).limit(max(limit, 1))
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    if timeframe is not None:
        stmt = stmt.where(Signal.timeframe == timeframe)
    rows = db.execute(stmt).all()
    return _serialize_signal_rows(db, rows)


def list_top_signals(db: Session, *, limit: int = 20) -> Sequence[dict[str, Any]]:
    rows = db.execute(
        _signal_select()
        .order_by(Signal.priority_score.desc(), Signal.candle_timestamp.desc(), Signal.created_at.desc())
        .limit(max(limit, 1))
    ).all()
    return _serialize_signal_rows(db, rows)


def list_coin_patterns(db: Session, symbol: str, *, limit: int = 200) -> Sequence[dict[str, Any]]:
    rows = db.execute(
        _signal_select()
        .where(Coin.symbol == symbol.upper(), Signal.signal_type.like("pattern_%"))
        .order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc())
        .limit(max(limit, 1))
    ).all()
    return _serialize_signal_rows(db, rows)


def get_coin_regimes(db: Session, symbol: str) -> dict[str, Any] | None:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        return None
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin.id))
    items = compute_live_regimes(db, coin.id)
    return {
        "coin_id": coin.id,
        "symbol": coin.symbol,
        "canonical_regime": metrics.market_regime if metrics is not None else None,
        "items": [
            {
                "timeframe": item.timeframe,
                "regime": item.regime,
                "confidence": item.confidence,
            }
            for item in items
        ],
    }


def list_sectors(db: Session) -> Sequence[dict[str, Any]]:
    rows = db.execute(
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
    ).all()
    return [dict(row._mapping) for row in rows]


def list_sector_metrics(db: Session, *, timeframe: int | None = None) -> dict[str, Any]:
    stmt = (
        select(
            SectorMetric.sector_id,
            Sector.name,
            Sector.description,
            SectorMetric.timeframe,
            SectorMetric.sector_strength,
            SectorMetric.relative_strength,
            SectorMetric.capital_flow,
            SectorMetric.volatility,
            SectorMetric.updated_at,
        )
        .join(Sector, Sector.id == SectorMetric.sector_id)
        .order_by(SectorMetric.timeframe.asc(), SectorMetric.relative_strength.desc())
    )
    if timeframe is not None:
        stmt = stmt.where(SectorMetric.timeframe == timeframe)
    rows = db.execute(stmt).all()
    return {
        "items": [dict(row._mapping) for row in rows],
        "narratives": [
            {
                "timeframe": item.timeframe,
                "top_sector": item.top_sector,
                "rotation_state": item.rotation_state,
                "btc_dominance": item.btc_dominance,
            }
            for item in build_sector_narratives(db)
            if timeframe is None or item.timeframe == timeframe
        ],
    }


def list_market_cycles(
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
) -> Sequence[dict[str, Any]]:
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
    rows = db.execute(stmt).all()
    return [dict(row._mapping) for row in rows]
