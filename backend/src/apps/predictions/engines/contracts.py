from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class PredictionWindowCandleInput:
    timestamp: datetime
    high: float
    low: float
    close: float


@dataclass(slots=True, frozen=True)
class PredictionWindowInput:
    expected_move: str
    deadline: datetime
    now: datetime
    candles: tuple[PredictionWindowCandleInput, ...]


__all__ = [
    "PredictionWindowCandleInput",
    "PredictionWindowInput",
]
