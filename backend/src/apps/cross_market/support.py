from __future__ import annotations

import math

RELATION_LOOKBACK = 200
RELATION_MIN_POINTS = 48
RELATION_MAX_LAG_HOURS = 8
RELATION_MIN_CORRELATION = 0.25
MATERIAL_RELATION_DELTA = 0.04
LEADER_SYMBOLS = ("BTCUSD", "ETHUSD", "SOLUSD")


def clamp_relation_value(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def close_returns(points: list[object]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(points, points[1:], strict=False):
        previous_close = float(previous.close)
        current_close = float(current.close)
        returns.append((current_close - previous_close) / previous_close if previous_close else 0.0)
    return returns


def pearson(values_a: list[float], values_b: list[float]) -> float:
    if len(values_a) != len(values_b) or len(values_a) < 3:
        return 0.0
    mean_a = sum(values_a) / len(values_a)
    mean_b = sum(values_b) / len(values_b)
    numerator = sum((left - mean_a) * (right - mean_b) for left, right in zip(values_a, values_b, strict=False))
    denominator_left = math.sqrt(sum((value - mean_a) ** 2 for value in values_a))
    denominator_right = math.sqrt(sum((value - mean_b) ** 2 for value in values_b))
    if denominator_left == 0 or denominator_right == 0:
        return 0.0
    return numerator / (denominator_left * denominator_right)


def best_lagged_correlation(
    leader_points: list[object],
    follower_points: list[object],
    *,
    timeframe: int,
) -> tuple[float, int, int]:
    leader_returns = close_returns(leader_points)
    follower_returns = close_returns(follower_points)
    size = min(len(leader_returns), len(follower_returns))
    if size < RELATION_MIN_POINTS:
        return 0.0, 0, size
    leader_returns = leader_returns[-size:]
    follower_returns = follower_returns[-size:]
    max_lag_bars = max(min(int((RELATION_MAX_LAG_HOURS * 60) / max(timeframe, 1)), 24), 0)
    best = (0.0, 0, size)
    for lag in range(0, max_lag_bars + 1):
        if lag == 0:
            current_leader = leader_returns
            current_follower = follower_returns
        else:
            current_leader = leader_returns[:-lag]
            current_follower = follower_returns[lag:]
        usable = min(len(current_leader), len(current_follower))
        if usable < RELATION_MIN_POINTS:
            continue
        correlation = pearson(current_leader[-usable:], current_follower[-usable:])
        if correlation > best[0]:
            lag_hours = max(int(round((lag * timeframe) / 60)), 1 if lag > 0 else 0)
            best = (correlation, lag_hours, usable)
    return best


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
