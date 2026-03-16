from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True, frozen=True)
class PredictionReadModel:
    id: int
    prediction_type: str
    leader_coin_id: int
    leader_symbol: str
    target_coin_id: int
    target_symbol: str
    prediction_event: str
    expected_move: str
    lag_hours: int
    confidence: float
    created_at: datetime
    evaluation_time: datetime
    status: str
    actual_move: float | None
    success: bool | None
    profit: float | None
    evaluated_at: datetime | None


def prediction_read_model_from_mapping(mapping: Mapping[str, Any]) -> PredictionReadModel:
    return PredictionReadModel(
        id=int(mapping["id"]),
        prediction_type=str(mapping["prediction_type"]),
        leader_coin_id=int(mapping["leader_coin_id"]),
        leader_symbol=str(mapping["leader_symbol"]),
        target_coin_id=int(mapping["target_coin_id"]),
        target_symbol=str(mapping["target_symbol"]),
        prediction_event=str(mapping["prediction_event"]),
        expected_move=str(mapping["expected_move"]),
        lag_hours=int(mapping["lag_hours"]),
        confidence=float(mapping["confidence"]),
        created_at=mapping["created_at"],
        evaluation_time=mapping["evaluation_time"],
        status=str(mapping["status"]),
        actual_move=float(mapping["actual_move"]) if mapping["actual_move"] is not None else None,
        success=bool(mapping["success"]) if mapping["success"] is not None else None,
        profit=float(mapping["profit"]) if mapping["profit"] is not None else None,
        evaluated_at=mapping["evaluated_at"],
    )


__all__ = [
    "PredictionReadModel",
    "prediction_read_model_from_mapping",
]
