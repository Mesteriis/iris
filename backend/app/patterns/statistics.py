from __future__ import annotations

from math import exp, log


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
