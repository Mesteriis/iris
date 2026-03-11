from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.coin import Coin
from app.models.coin_metrics import CoinMetrics
from app.models.market_cycle import MarketCycle
from app.models.sector_metric import SectorMetric
from app.models.signal import Signal
from app.services.market_data import utc_now

MARKET_CYCLE_PHASES = [
    "ACCUMULATION",
    "EARLY_MARKUP",
    "MARKUP",
    "LATE_MARKUP",
    "DISTRIBUTION",
    "EARLY_MARKDOWN",
    "MARKDOWN",
    "CAPITULATION",
]


def _detect_cycle_phase(
    *,
    trend_score: int | None,
    regime: str | None,
    volatility: float | None,
    price_current: float | None,
    pattern_density: int,
    cluster_frequency: int,
    sector_strength: float | None,
    capital_flow: float | None,
) -> tuple[str, float]:
    normalized_volatility = (volatility or 0.0) / max(price_current or 1.0, 1e-9)
    if regime == "high_volatility" and normalized_volatility > 0.05 and (trend_score or 0) < 20:
        return "CAPITULATION", 0.82
    if regime in {"sideways_range", "low_volatility"} and 40 <= (trend_score or 50) <= 60 and (capital_flow or 0.0) >= -0.02:
        return "ACCUMULATION", 0.7
    if regime == "bull_trend" and (trend_score or 0) >= 60 and pattern_density >= 2 and (sector_strength or 0.0) >= 0:
        return ("MARKUP", 0.84) if cluster_frequency >= 1 else ("EARLY_MARKUP", 0.76)
    if regime == "bull_trend" and normalized_volatility >= 0.04:
        return "LATE_MARKUP", 0.74
    if regime in {"bear_trend", "high_volatility"} and (trend_score or 100) <= 45:
        return ("MARKDOWN", 0.8) if cluster_frequency >= 1 else ("EARLY_MARKDOWN", 0.72)
    if regime == "sideways_range" and normalized_volatility >= 0.03:
        return "DISTRIBUTION", 0.7
    return "ACCUMULATION", 0.55


def update_market_cycle(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
) -> dict[str, object]:
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
    coin = db.get(Coin, coin_id)
    if metrics is None or coin is None:
        return {"status": "skipped", "reason": "coin_metrics_not_found", "coin_id": coin_id}

    pattern_density = int(
        db.scalar(
            select(func.count())
            .select_from(Signal)
            .where(
                Signal.coin_id == coin_id,
                Signal.timeframe == timeframe,
                Signal.signal_type.like("pattern_%"),
                ~Signal.signal_type.like("pattern_cluster_%"),
                ~Signal.signal_type.like("pattern_hierarchy_%"),
            )
        )
        or 0
    )
    cluster_frequency = int(
        db.scalar(
            select(func.count())
            .select_from(Signal)
            .where(
                Signal.coin_id == coin_id,
                Signal.timeframe == timeframe,
                Signal.signal_type.like("pattern_cluster_%"),
            )
        )
        or 0
    )
    sector_metric = None
    if coin.sector_id is not None:
        sector_metric = db.get(SectorMetric, (coin.sector_id, timeframe))
    phase, confidence = _detect_cycle_phase(
        trend_score=metrics.trend_score,
        regime=metrics.market_regime,
        volatility=metrics.volatility,
        price_current=metrics.price_current,
        pattern_density=pattern_density,
        cluster_frequency=cluster_frequency,
        sector_strength=sector_metric.sector_strength if sector_metric is not None else None,
        capital_flow=sector_metric.capital_flow if sector_metric is not None else None,
    )
    stmt = insert(MarketCycle).values(
        {
            "coin_id": coin_id,
            "timeframe": timeframe,
            "cycle_phase": phase,
            "confidence": confidence,
            "detected_at": utc_now(),
        }
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["coin_id", "timeframe"],
        set_={
            "cycle_phase": stmt.excluded.cycle_phase,
            "confidence": stmt.excluded.confidence,
            "detected_at": stmt.excluded.detected_at,
        },
    )
    db.execute(stmt)
    db.commit()
    return {"status": "ok", "coin_id": coin_id, "timeframe": timeframe, "cycle_phase": phase, "confidence": confidence}


def refresh_market_cycles(db: Session) -> dict[str, object]:
    coins = db.scalars(select(Coin).where(Coin.enabled.is_(True), Coin.deleted_at.is_(None))).all()
    items = [update_market_cycle(db, coin_id=coin.id, timeframe=timeframe) for coin in coins for timeframe in (15, 60, 240, 1440)]
    return {"status": "ok", "items": items, "cycles": len(items)}
