from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.apps.predictions.cache import PredictionCacheEntry
from src.apps.predictions.models import MarketPrediction


@dataclass(slots=True, frozen=True)
class PredictionCacheSnapshot:
    prediction_id: int
    prediction_type: str
    leader_coin_id: int
    target_coin_id: int
    prediction_event: str
    expected_move: str
    lag_hours: int
    confidence: float
    created_at: datetime | None
    evaluation_time: datetime | None
    status: str

    @classmethod
    def from_prediction(cls, prediction: MarketPrediction) -> PredictionCacheSnapshot:
        return cls(
            prediction_id=int(prediction.id),
            prediction_type=prediction.prediction_type,
            leader_coin_id=int(prediction.leader_coin_id),
            target_coin_id=int(prediction.target_coin_id),
            prediction_event=prediction.prediction_event,
            expected_move=prediction.expected_move,
            lag_hours=int(prediction.lag_hours),
            confidence=float(prediction.confidence),
            created_at=prediction.created_at,
            evaluation_time=prediction.evaluation_time,
            status=prediction.status,
        )

    @classmethod
    def from_cache_entry(cls, entry: PredictionCacheEntry) -> PredictionCacheSnapshot:
        return cls(
            prediction_id=int(entry.id),
            prediction_type=entry.prediction_type,
            leader_coin_id=int(entry.leader_coin_id),
            target_coin_id=int(entry.target_coin_id),
            prediction_event=entry.prediction_event,
            expected_move=entry.expected_move,
            lag_hours=int(entry.lag_hours),
            confidence=float(entry.confidence),
            created_at=entry.created_at,
            evaluation_time=entry.evaluation_time,
            status=entry.status,
        )

    def as_cache_kwargs(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "prediction_type": self.prediction_type,
            "leader_coin_id": self.leader_coin_id,
            "target_coin_id": self.target_coin_id,
            "prediction_event": self.prediction_event,
            "expected_move": self.expected_move,
            "lag_hours": self.lag_hours,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "evaluation_time": self.evaluation_time,
            "status": self.status,
        }


@dataclass(slots=True, frozen=True)
class PredictionPublishedEvent:
    event_type: str
    payload: Mapping[str, Any]


@dataclass(slots=True, frozen=True)
class PredictionCreationBatch:
    status: str
    leader_coin_id: int
    created: int = 0
    reason: str | None = None
    cache_snapshots: tuple[PredictionCacheSnapshot, ...] = ()


@dataclass(slots=True, frozen=True)
class PredictionEvaluationBatch:
    status: str
    evaluated: int
    confirmed: int
    failed: int
    expired: int
    cache_snapshots: tuple[PredictionCacheSnapshot, ...] = ()
    events: tuple[PredictionPublishedEvent, ...] = ()


__all__ = [
    "PredictionCacheSnapshot",
    "PredictionCreationBatch",
    "PredictionEvaluationBatch",
    "PredictionPublishedEvent",
]
