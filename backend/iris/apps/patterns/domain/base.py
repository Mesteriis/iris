from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from iris.apps.market_data.candles import CandlePoint


@dataclass(slots=True, frozen=True)
class PatternDetection:
    slug: str
    signal_type: str
    confidence: float
    candle_timestamp: datetime
    category: str
    attributes: dict[str, Any] = field(default_factory=dict)


class PatternDetector(ABC):
    slug = "base_pattern"
    category = "generic"
    supported_timeframes = [15, 60, 240, 1440]
    required_indicators: list[str] = []
    enabled = True

    @abstractmethod
    def detect(
        self,
        candles: Sequence[CandlePoint],
        indicators: dict[str, float | None],
    ) -> list[PatternDetection]:
        raise NotImplementedError
