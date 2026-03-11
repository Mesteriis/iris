from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.apps.indicators.models import CoinMetrics
from app.apps.signals.models import Signal
from app.apps.patterns.domain.base import PatternDetection
from app.apps.patterns.domain.registry import feature_enabled
from app.apps.patterns.domain.semantics import (
    BEARISH_PATTERN_SLUGS,
    BULLISH_PATTERN_SLUGS,
    is_cluster_signal,
    is_pattern_signal,
    slug_from_signal_type,
)
from app.apps.market_data.domain import ensure_utc

HIERARCHY_SIGNAL_TYPES = {
    "accumulation": "pattern_hierarchy_accumulation",
    "distribution": "pattern_hierarchy_distribution",
    "trend_continuation": "pattern_hierarchy_trend_continuation",
    "trend_exhaustion": "pattern_hierarchy_trend_exhaustion",
}


def _insert_hierarchy_signal(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    detection: PatternDetection,
    market_regime: str | None = None,
) -> int:
    stmt = insert(Signal).values(
        {
            "coin_id": coin_id,
            "timeframe": timeframe,
            "signal_type": detection.signal_type,
            "confidence": detection.confidence,
            "priority_score": 0.0,
            "context_score": 1.0,
            "regime_alignment": 1.0,
            "market_regime": market_regime,
            "candle_timestamp": detection.candle_timestamp,
        }
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["coin_id", "timeframe", "candle_timestamp", "signal_type"])
    result = db.execute(stmt)
    db.commit()
    return int(result.rowcount or 0)


def build_hierarchy_signals(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    candle_timestamp: object,
) -> dict[str, object]:
    if not feature_enabled(db, "pattern_hierarchy"):
        return {"status": "skipped", "reason": "pattern_hierarchy_disabled"}

    window_start = ensure_utc(candle_timestamp) - timedelta(days=14)
    signals = db.scalars(
        select(Signal).where(
            Signal.coin_id == coin_id,
            Signal.timeframe == timeframe,
            Signal.candle_timestamp >= window_start,
            Signal.candle_timestamp <= candle_timestamp,
        )
    ).all()
    pattern_signals = [signal for signal in signals if is_pattern_signal(signal.signal_type)]
    cluster_signals = [signal for signal in signals if is_cluster_signal(signal.signal_type)]
    if not pattern_signals:
        return {"status": "skipped", "reason": "pattern_signals_not_found"}

    bullish = sum(1 for signal in pattern_signals if (slug_from_signal_type(signal.signal_type) or "") in BULLISH_PATTERN_SLUGS)
    bearish = sum(1 for signal in pattern_signals if (slug_from_signal_type(signal.signal_type) or "") in BEARISH_PATTERN_SLUGS)
    exhaustion = sum(1 for signal in pattern_signals if signal.signal_type in {"pattern_momentum_exhaustion", "pattern_volume_climax"})
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))

    detections: list[PatternDetection] = []
    if metrics is not None and (metrics.trend_score or 50) >= 55 and bullish >= 2 and cluster_signals:
        detections.append(
            PatternDetection(
                slug="trend_continuation",
                signal_type=HIERARCHY_SIGNAL_TYPES["trend_continuation"],
                confidence=0.78,
                candle_timestamp=candle_timestamp,
                category="hierarchy",
            )
        )
    if metrics is not None and (metrics.trend_score or 50) <= 45 and bearish >= 2 and cluster_signals:
        detections.append(
            PatternDetection(
                slug="distribution",
                signal_type=HIERARCHY_SIGNAL_TYPES["distribution"],
                confidence=0.74,
                candle_timestamp=candle_timestamp,
                category="hierarchy",
            )
        )
    if metrics is not None and (metrics.volatility or 0) < (metrics.price_current or 1) * 0.03 and bullish >= bearish and bullish >= 2:
        detections.append(
            PatternDetection(
                slug="accumulation",
                signal_type=HIERARCHY_SIGNAL_TYPES["accumulation"],
                confidence=0.7,
                candle_timestamp=candle_timestamp,
                category="hierarchy",
            )
        )
    if exhaustion >= 2:
        detections.append(
            PatternDetection(
                slug="trend_exhaustion",
                signal_type=HIERARCHY_SIGNAL_TYPES["trend_exhaustion"],
                confidence=0.73,
                candle_timestamp=candle_timestamp,
                category="hierarchy",
            )
        )

    created = sum(
        _insert_hierarchy_signal(
            db,
            coin_id=coin_id,
            timeframe=timeframe,
            detection=detection,
            market_regime=metrics.market_regime if metrics is not None else None,
        )
        for detection in detections
    )
    return {"status": "ok", "created": created}
