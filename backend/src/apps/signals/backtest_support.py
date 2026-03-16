from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from typing import Any
from collections.abc import Sequence


@dataclass(slots=True, frozen=True)
class BacktestPoint:
    symbol: str
    signal_type: str
    timeframe: int
    confidence: float
    result_return: float
    result_drawdown: float
    evaluated_at: datetime | None


def clamp_backtest_value(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def sharpe_ratio(returns: Sequence[float]) -> float:
    if len(returns) < 2:
        return 0.0
    avg = sum(returns) / len(returns)
    variance = sum((value - avg) ** 2 for value in returns) / len(returns)
    if variance <= 0:
        return 0.0
    return avg / sqrt(variance)


def serialize_backtest_group(
    *,
    symbol: str | None,
    signal_type: str,
    timeframe: int,
    points: Sequence[BacktestPoint],
) -> dict[str, Any]:
    sample_size = len(points)
    returns = [point.result_return for point in points]
    drawdowns = [point.result_drawdown for point in points]
    confidences = [point.confidence for point in points]
    symbols = {point.symbol for point in points}
    win_rate = sum(1 for value in returns if value > 0) / sample_size if sample_size else 0.0
    avg_return = sum(returns) / sample_size if sample_size else 0.0
    return {
        "symbol": symbol,
        "signal_type": signal_type,
        "timeframe": timeframe,
        "sample_size": sample_size,
        "coin_count": len(symbols),
        "win_rate": win_rate,
        "roi": sum(returns),
        "avg_return": avg_return,
        "sharpe_ratio": sharpe_ratio(returns),
        "max_drawdown": min(drawdowns) if drawdowns else 0.0,
        "avg_confidence": sum(confidences) / sample_size if sample_size else 0.0,
        "last_evaluated_at": max((point.evaluated_at for point in points), default=None),
    }


__all__ = [
    "BacktestPoint",
    "clamp_backtest_value",
    "serialize_backtest_group",
    "sharpe_ratio",
]
