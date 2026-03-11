from __future__ import annotations


def calculate_priority_score(
    *,
    confidence: float,
    pattern_temperature: float,
    regime_alignment: float,
    volatility_alignment: float,
    liquidity_score: float,
) -> float:
    return confidence * pattern_temperature * regime_alignment * volatility_alignment * liquidity_score
