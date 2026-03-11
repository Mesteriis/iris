from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.coin_metrics import CoinMetrics
from app.models.signal import Signal
from app.patterns.base import PatternDetection
from app.patterns.registry import feature_enabled
from app.patterns.semantics import BEARISH_PATTERN_SLUGS, BULLISH_PATTERN_SLUGS, is_pattern_signal, slug_from_signal_type

CLUSTER_SIGNAL_TYPES = {
    "bullish": "pattern_cluster_bullish",
    "bearish": "pattern_cluster_bearish",
}


def _insert_cluster_signal(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    detection: PatternDetection,
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
            "candle_timestamp": detection.candle_timestamp,
        }
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["coin_id", "timeframe", "candle_timestamp", "signal_type"])
    result = db.execute(stmt)
    db.commit()
    return int(result.rowcount or 0)


def build_pattern_clusters(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    candle_timestamp: object,
) -> dict[str, object]:
    if not feature_enabled(db, "pattern_clusters"):
        return {"status": "skipped", "reason": "pattern_clusters_disabled"}

    signals = db.scalars(
        select(Signal).where(
            Signal.coin_id == coin_id,
            Signal.timeframe == timeframe,
            Signal.candle_timestamp == candle_timestamp,
        )
    ).all()
    pattern_signals = [signal for signal in signals if is_pattern_signal(signal.signal_type)]
    if not pattern_signals:
        return {"status": "skipped", "reason": "pattern_signals_not_found"}

    bullish = [signal for signal in pattern_signals if (slug_from_signal_type(signal.signal_type) or "") in BULLISH_PATTERN_SLUGS]
    bearish = [signal for signal in pattern_signals if (slug_from_signal_type(signal.signal_type) or "") in BEARISH_PATTERN_SLUGS]
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))

    created = 0
    if bullish and any(signal.signal_type == "pattern_volume_spike" for signal in pattern_signals) and metrics is not None and (metrics.trend_score or 0) >= 60:
        confidence = min(sum(signal.confidence for signal in bullish) / len(bullish) + 0.12, 0.95)
        created += _insert_cluster_signal(
            db,
            coin_id=coin_id,
            timeframe=timeframe,
            detection=PatternDetection(
                slug="cluster_bullish",
                signal_type=CLUSTER_SIGNAL_TYPES["bullish"],
                confidence=confidence,
                candle_timestamp=candle_timestamp,
                category="cluster",
            ),
        )
    if bearish and any(signal.signal_type in {"pattern_volume_spike", "pattern_volume_climax"} for signal in pattern_signals) and metrics is not None and (metrics.trend_score or 100) <= 40:
        confidence = min(sum(signal.confidence for signal in bearish) / len(bearish) + 0.12, 0.95)
        created += _insert_cluster_signal(
            db,
            coin_id=coin_id,
            timeframe=timeframe,
            detection=PatternDetection(
                slug="cluster_bearish",
                signal_type=CLUSTER_SIGNAL_TYPES["bearish"],
                confidence=confidence,
                candle_timestamp=candle_timestamp,
                category="cluster",
            ),
        )
    return {"status": "ok", "created": created}
