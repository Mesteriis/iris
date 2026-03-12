from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from polyfactory.factories.dataclass_factory import DataclassFactory
from polyfactory.fields import Use

from tests.factories.base import fake


@dataclass
class SignalHistorySeed:
    timeframe: int
    signal_type: str
    confidence: float
    market_regime: str
    candle_timestamp: datetime
    result_return: float | None
    result_drawdown: float | None
    evaluated_at: datetime | None
    profit_after_24h: float | None = None
    profit_after_72h: float | None = None
    maximum_drawdown: float | None = None


class SignalHistorySeedFactory(DataclassFactory[SignalHistorySeed]):
    __check_model__ = False

    timeframe = Use(lambda: fake.random_element(elements=(15, 60, 240)))
    signal_type = Use(lambda: fake.random_element(elements=("pattern_bull_flag", "golden_cross", "death_cross")))
    confidence = Use(lambda: round(fake.pyfloat(min_value=0.5, max_value=0.99, positive=True), 2))
    market_regime = Use(lambda: fake.random_element(elements=("bull_trend", "bear_trend", "sideways_range")))
    result_return = Use(lambda: round(fake.pyfloat(min_value=-0.2, max_value=0.2), 3))
    result_drawdown = Use(lambda: round(fake.pyfloat(min_value=-0.2, max_value=-0.001), 3))
    profit_after_24h = None
    profit_after_72h = None
    maximum_drawdown = None
