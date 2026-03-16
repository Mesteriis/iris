MARKET_CYCLE_PHASES = [
    "ACCUMULATION",
    "EARLY_MARKUP",
    "MARKUP",
    "LATE_MARKUP",
    "DISTRIBUTION",
    "EARLY_MARKDOWN",
    "MARKDOWN",
    "CAPITULATION",
]


def _detect_cycle_phase(
    *,
    trend_score: int | None,
    regime: str | None,
    volatility: float | None,
    price_current: float | None,
    pattern_density: int,
    cluster_frequency: int,
    sector_strength: float | None,
    capital_flow: float | None,
) -> tuple[str, float]:
    normalized_volatility = (volatility or 0.0) / max(price_current or 1.0, 1e-9)
    if regime == "high_volatility" and normalized_volatility > 0.05 and (trend_score or 0) < 20:
        return "CAPITULATION", 0.82
    if regime in {"sideways_range", "low_volatility"} and 40 <= (trend_score or 50) <= 60 and (capital_flow or 0.0) >= -0.02:
        return "ACCUMULATION", 0.7
    if regime == "bull_trend" and (trend_score or 0) >= 60 and pattern_density >= 2 and (sector_strength or 0.0) >= 0:
        return ("MARKUP", 0.84) if cluster_frequency >= 1 else ("EARLY_MARKUP", 0.76)
    if regime == "bull_trend" and normalized_volatility >= 0.04:
        return "LATE_MARKUP", 0.74
    if regime in {"bear_trend", "high_volatility"} and (trend_score or 100) <= 45:
        return ("MARKDOWN", 0.8) if cluster_frequency >= 1 else ("EARLY_MARKDOWN", 0.72)
    if regime == "sideways_range" and normalized_volatility >= 0.03:
        return "DISTRIBUTION", 0.7
    return "ACCUMULATION", 0.55
