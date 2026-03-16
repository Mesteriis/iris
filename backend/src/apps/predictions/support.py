from dataclasses import dataclass

PREDICTION_MOVE_THRESHOLD = 0.015
PREDICTION_MAX_FOLLOWERS = 8


@dataclass(slots=True, frozen=True)
class PredictionOutcome:
    status: str
    actual_move: float
    success: bool
    profit: float


def clamp_prediction_value(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


__all__ = [
    "PREDICTION_MAX_FOLLOWERS",
    "PREDICTION_MOVE_THRESHOLD",
    "PredictionOutcome",
    "clamp_prediction_value",
]
