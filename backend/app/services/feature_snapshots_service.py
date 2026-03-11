from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.coin import Coin
from app.models.coin_metrics import CoinMetrics
from app.models.feature_snapshot import FeatureSnapshot
from app.models.market_cycle import MarketCycle
from app.models.sector_metric import SectorMetric
from app.models.signal import Signal
from app.patterns.regime import read_regime_details
from app.patterns.semantics import is_cluster_signal, is_pattern_signal


def capture_feature_snapshot(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    timestamp: object,
    price_current: float | None,
    rsi_14: float | None,
    macd: float | None,
    commit: bool = True,
) -> dict[str, object]:
    coin = db.get(Coin, coin_id)
    if coin is None:
        return {"status": "skipped", "reason": "coin_not_found", "coin_id": coin_id, "timeframe": timeframe}

    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
    sector_metric = db.get(SectorMetric, (coin.sector_id, timeframe)) if coin.sector_id is not None else None
    cycle = db.get(MarketCycle, (coin_id, timeframe))
    signal_rows = db.execute(
        select(Signal.signal_type, Signal.priority_score, Signal.confidence).where(
            Signal.coin_id == coin_id,
            Signal.timeframe == timeframe,
            Signal.candle_timestamp == timestamp,
            Signal.signal_type.like("pattern_%"),
        )
    ).all()

    pattern_density = sum(1 for row in signal_rows if is_pattern_signal(str(row.signal_type)))
    cluster_score = sum(
        float(row.priority_score or row.confidence or 0.0)
        for row in signal_rows
        if is_cluster_signal(str(row.signal_type))
    )
    regime_snapshot = (
        read_regime_details(metrics.market_regime_details, timeframe)
        if metrics is not None and metrics.market_regime_details
        else None
    )

    payload = {
        "coin_id": coin_id,
        "timeframe": timeframe,
        "timestamp": timestamp,
        "price_current": price_current,
        "rsi_14": rsi_14,
        "macd": macd,
        "trend_score": metrics.trend_score if metrics is not None else None,
        "volatility": float(metrics.volatility) if metrics is not None and metrics.volatility is not None else None,
        "sector_strength": (
            float(sector_metric.sector_strength)
            if sector_metric is not None and sector_metric.sector_strength is not None
            else None
        ),
        "market_regime": regime_snapshot.regime if regime_snapshot is not None else (metrics.market_regime if metrics is not None else None),
        "cycle_phase": cycle.cycle_phase if cycle is not None else None,
        "pattern_density": pattern_density,
        "cluster_score": cluster_score,
    }
    stmt = insert(FeatureSnapshot).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["coin_id", "timeframe", "timestamp"],
        set_={
            "price_current": stmt.excluded.price_current,
            "rsi_14": stmt.excluded.rsi_14,
            "macd": stmt.excluded.macd,
            "trend_score": stmt.excluded.trend_score,
            "volatility": stmt.excluded.volatility,
            "sector_strength": stmt.excluded.sector_strength,
            "market_regime": stmt.excluded.market_regime,
            "cycle_phase": stmt.excluded.cycle_phase,
            "pattern_density": stmt.excluded.pattern_density,
            "cluster_score": stmt.excluded.cluster_score,
        },
    )
    db.execute(stmt)
    if commit:
        db.commit()
    return {"status": "ok", **payload}
