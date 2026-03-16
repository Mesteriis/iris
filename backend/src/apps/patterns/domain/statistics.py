from dataclasses import dataclass
from datetime import datetime
from math import exp, log

from src.apps.market_data.domain import utc_now
from src.apps.patterns.domain.success import PATTERN_SUCCESS_ROLLING_WINDOW
from src.apps.signals.models import SignalHistory

STATISTICS_LOOKBACK_DAYS = 365
SUPPORTED_STATISTIC_TIMEFRAMES = (15, 60, 240, 1440)


@dataclass(slots=True)
class PatternOutcome:
    pattern_slug: str
    timeframe: int
    market_regime: str
    terminal_return: float
    drawdown: float
    success: bool
    age_days: int
    evaluated_at: datetime | None


def calculate_temperature(
    *,
    success_rate: float,
    sample_size: int,
    days_since_sample: int,
) -> float:
    if sample_size <= 0:
        return 0.0
    base = (success_rate - 0.5) * log(max(sample_size, 1))
    return base * exp(-(max(days_since_sample, 0) / 90))


def _select_return(row: SignalHistory) -> float | None:
    if row.profit_after_72h is not None:
        return float(row.profit_after_72h)
    if row.profit_after_24h is not None:
        return float(row.profit_after_24h)
    if row.result_return is not None:
        return float(row.result_return)
    return None


def _select_drawdown(row: SignalHistory) -> float | None:
    if row.maximum_drawdown is not None:
        return float(row.maximum_drawdown)
    if row.result_drawdown is not None:
        return float(row.result_drawdown)
    return None


def _rolling_window(
    outcomes_by_scope: dict[tuple[str, int, str], list[PatternOutcome]],
) -> dict[tuple[str, int, str], list[PatternOutcome]]:
    limited: dict[tuple[str, int, str], list[PatternOutcome]] = {}
    for scope, outcomes in outcomes_by_scope.items():
        ordered = sorted(outcomes, key=lambda item: item.evaluated_at or utc_now())
        limited[scope] = ordered[-PATTERN_SUCCESS_ROLLING_WINDOW:]
    return limited


__all__ = [
    "STATISTICS_LOOKBACK_DAYS",
    "SUPPORTED_STATISTIC_TIMEFRAMES",
    "PatternOutcome",
    "_rolling_window",
    "_select_drawdown",
    "_select_return",
    "calculate_temperature",
]
