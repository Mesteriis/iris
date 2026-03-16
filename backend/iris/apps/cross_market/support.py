from collections.abc import Sequence
from typing import Protocol

from iris.apps.cross_market.engines import best_lagged_correlation as _best_lagged_correlation
from iris.apps.cross_market.engines import close_returns as _close_returns
from iris.apps.cross_market.engines import pearson as _pearson

RELATION_LOOKBACK = 200
RELATION_MIN_POINTS = 48
RELATION_MAX_LAG_HOURS = 8
RELATION_MIN_CORRELATION = 0.25
MATERIAL_RELATION_DELTA = 0.04
LEADER_SYMBOLS = ("BTCUSD", "ETHUSD", "SOLUSD")


class _ClosePoint(Protocol):
    close: float


def clamp_relation_value(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def close_returns(points: Sequence[_ClosePoint]) -> list[float]:
    return list(_close_returns(tuple(float(point.close) for point in points)))


def pearson(values_a: list[float], values_b: list[float]) -> float:
    return _pearson(tuple(values_a), tuple(values_b))


def best_lagged_correlation(
    leader_points: Sequence[_ClosePoint],
    follower_points: Sequence[_ClosePoint],
    *,
    timeframe: int,
) -> tuple[float, int, int]:
    return _best_lagged_correlation(
        leader_closes=tuple(float(point.close) for point in leader_points),
        follower_closes=tuple(float(point.close) for point in follower_points),
        timeframe=timeframe,
        min_points=RELATION_MIN_POINTS,
        max_lag_hours=RELATION_MAX_LAG_HOURS,
    )


def relation_timeframe(timeframe: int) -> int:
    return 60 if timeframe < 60 else timeframe


__all__ = [
    "LEADER_SYMBOLS",
    "MATERIAL_RELATION_DELTA",
    "RELATION_LOOKBACK",
    "RELATION_MAX_LAG_HOURS",
    "RELATION_MIN_CORRELATION",
    "RELATION_MIN_POINTS",
    "best_lagged_correlation",
    "clamp_relation_value",
    "close_returns",
    "pearson",
    "relation_timeframe",
]
