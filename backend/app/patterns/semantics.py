from __future__ import annotations

BULLISH_PATTERN_SLUGS = {
    "inverse_head_shoulders",
    "double_bottom",
    "triple_bottom",
    "ascending_triangle",
    "falling_wedge",
    "bull_flag",
    "pennant",
    "cup_and_handle",
    "breakout_retest",
    "consolidation_breakout",
    "rsi_divergence",
    "macd_cross",
    "macd_divergence",
    "bollinger_squeeze",
    "bollinger_expansion",
    "cluster_bullish",
    "accumulation",
    "trend_continuation",
}

BEARISH_PATTERN_SLUGS = {
    "head_shoulders",
    "double_top",
    "triple_top",
    "descending_triangle",
    "rising_wedge",
    "bear_flag",
    "momentum_exhaustion",
    "atr_spike",
    "volume_climax",
    "cluster_bearish",
    "distribution",
    "trend_exhaustion",
}

NEUTRAL_PATTERN_SLUGS = {
    "symmetrical_triangle",
    "volume_spike",
    "volume_divergence",
}


def slug_from_signal_type(signal_type: str) -> str | None:
    if signal_type.startswith("pattern_"):
        return signal_type.removeprefix("pattern_")
    return None


def is_pattern_signal(signal_type: str) -> bool:
    return signal_type.startswith("pattern_") and not is_cluster_signal(signal_type) and not is_hierarchy_signal(signal_type)


def is_cluster_signal(signal_type: str) -> bool:
    return signal_type.startswith("pattern_cluster_")


def is_hierarchy_signal(signal_type: str) -> bool:
    return signal_type.startswith("pattern_hierarchy_")


def pattern_bias(slug: str, fallback_price_delta: float = 0.0) -> int:
    if slug.startswith("cluster_"):
        slug = slug.removeprefix("cluster_")
    if slug.startswith("hierarchy_"):
        slug = slug.removeprefix("hierarchy_")
    if slug in BULLISH_PATTERN_SLUGS:
        return 1
    if slug in BEARISH_PATTERN_SLUGS:
        return -1
    return 1 if fallback_price_delta >= 0 else -1
