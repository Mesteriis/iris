from __future__ import annotations

from datetime import datetime

from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.patterns.domain.base import PatternDetection
from src.apps.patterns.engines.contracts import PatternSignalInsertSpec


def build_detection_rows(
    *,
    coin_id: int,
    timeframe: int,
    detections: list[PatternDetection],
) -> list[dict[str, object]]:
    return [
        {
            "coin_id": int(coin_id),
            "timeframe": int(timeframe),
            "signal_type": detection.signal_type,
            "confidence": detection.confidence,
            "priority_score": 0.0,
            "context_score": 1.0,
            "regime_alignment": 1.0,
            "market_regime": str(detection.attributes.get("regime"))
            if detection.attributes.get("regime") is not None
            else None,
            "candle_timestamp": detection.candle_timestamp,
        }
        for detection in detections
    ]


def build_signal_rows_from_specs(
    *,
    coin_id: int,
    timeframe: int,
    candle_timestamp: datetime,
    specs: tuple[PatternSignalInsertSpec, ...],
) -> list[dict[str, object]]:
    return [
        {
            "coin_id": int(coin_id),
            "timeframe": int(timeframe),
            "signal_type": spec.signal_type,
            "confidence": float(spec.confidence),
            "priority_score": 0.0,
            "context_score": 1.0,
            "regime_alignment": 1.0,
            "market_regime": spec.market_regime,
            "candle_timestamp": candle_timestamp,
        }
        for spec in specs
    ]


def normalize_runtime_timestamp(value: object | None) -> datetime:
    if value is None:
        return utc_now()
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, str):
        return ensure_utc(datetime.fromisoformat(value))
    return utc_now()


__all__ = [
    "build_detection_rows",
    "build_signal_rows_from_specs",
    "normalize_runtime_timestamp",
]
