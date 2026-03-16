import math
from itertools import pairwise

from src.apps.cross_market.engines.contracts import CrossMarketRelationAnalysisResult

_PEARSON_DEGENERATE_ABS_TOLERANCE = 1e-12
_PEARSON_DEGENERATE_REL_TOLERANCE = 1e-9


def close_returns(closes: tuple[float, ...]) -> tuple[float, ...]:
    returns: list[float] = []
    for previous, current in pairwise(closes):
        returns.append((current - previous) / previous if previous else 0.0)
    return tuple(returns)


def _degenerate_pearson(values_a: tuple[float, ...], values_b: tuple[float, ...]) -> float:
    if all(
        math.isclose(left, right, rel_tol=_PEARSON_DEGENERATE_REL_TOLERANCE, abs_tol=_PEARSON_DEGENERATE_ABS_TOLERANCE)
        for left, right in zip(values_a, values_b, strict=False)
    ):
        return 1.0
    if all(
        math.isclose(left, -right, rel_tol=_PEARSON_DEGENERATE_REL_TOLERANCE, abs_tol=_PEARSON_DEGENERATE_ABS_TOLERANCE)
        for left, right in zip(values_a, values_b, strict=False)
    ):
        return -1.0
    return 0.0


def pearson(values_a: tuple[float, ...], values_b: tuple[float, ...]) -> float:
    if len(values_a) != len(values_b) or len(values_a) < 3:
        return 0.0
    mean_a = sum(values_a) / len(values_a)
    mean_b = sum(values_b) / len(values_b)
    numerator = sum((left - mean_a) * (right - mean_b) for left, right in zip(values_a, values_b, strict=False))
    denominator_left = math.sqrt(sum((value - mean_a) ** 2 for value in values_a))
    denominator_right = math.sqrt(sum((value - mean_b) ** 2 for value in values_b))
    if math.isclose(denominator_left, 0.0, abs_tol=_PEARSON_DEGENERATE_ABS_TOLERANCE) or math.isclose(
        denominator_right, 0.0, abs_tol=_PEARSON_DEGENERATE_ABS_TOLERANCE
    ):
        return _degenerate_pearson(values_a, values_b)
    return numerator / (denominator_left * denominator_right)


def best_lagged_correlation(
    leader_closes: tuple[float, ...],
    follower_closes: tuple[float, ...],
    *,
    timeframe: int,
    min_points: int,
    max_lag_hours: int,
) -> tuple[float, int, int]:
    leader_returns = close_returns(leader_closes)
    follower_returns = close_returns(follower_closes)
    size = min(len(leader_returns), len(follower_returns))
    if size < min_points:
        return 0.0, 0, size
    leader_returns = leader_returns[-size:]
    follower_returns = follower_returns[-size:]
    max_lag_bars = max(min(int((max_lag_hours * 60) / max(timeframe, 1)), 24), 0)
    best = (0.0, 0, size)
    for lag in range(0, max_lag_bars + 1):
        if lag == 0:
            current_leader = leader_returns
            current_follower = follower_returns
        else:
            current_leader = leader_returns[:-lag]
            current_follower = follower_returns[lag:]
        usable = min(len(current_leader), len(current_follower))
        if usable < min_points:
            continue
        correlation = pearson(current_leader[-usable:], current_follower[-usable:])
        if correlation > best[0]:
            lag_hours = max(round((lag * timeframe) / 60), 1 if lag > 0 else 0)
            best = (correlation, lag_hours, usable)
    return best


def evaluate_relation_candidate(
    *,
    leader_closes: tuple[float, ...],
    follower_closes: tuple[float, ...],
    timeframe: int,
    lookback: int,
    min_points: int,
    min_correlation: float,
    max_lag_hours: int,
) -> CrossMarketRelationAnalysisResult | None:
    correlation, lag_hours, sample_size = best_lagged_correlation(
        leader_closes=leader_closes,
        follower_closes=follower_closes,
        timeframe=timeframe,
        min_points=min_points,
        max_lag_hours=max_lag_hours,
    )
    if correlation < min_correlation:
        return None
    confidence = max(0.2, min(correlation * min(sample_size / max(lookback, 1), 1.0), 0.99))
    return CrossMarketRelationAnalysisResult(
        correlation=float(correlation),
        lag_hours=int(lag_hours),
        sample_size=int(sample_size),
        confidence=float(confidence),
    )


__all__ = [
    "best_lagged_correlation",
    "close_returns",
    "evaluate_relation_candidate",
    "pearson",
]
