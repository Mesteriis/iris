BULLISH_PATTERN_SLUGS = {
    "inverse_head_shoulders",
    "double_bottom",
    "triple_bottom",
    "ascending_triangle",
    "falling_wedge",
    "rectangle_bottom",
    "broadening_bottom",
    "descending_channel_breakout",
    "rounded_bottom",
    "diamond_bottom",
    "flat_base",
    "bull_flag",
    "pennant",
    "cup_and_handle",
    "breakout_retest",
    "consolidation_breakout",
    "high_tight_flag",
    "falling_channel_breakout",
    "measured_move_bullish",
    "base_breakout",
    "volatility_contraction_breakout",
    "pullback_continuation_bullish",
    "squeeze_breakout",
    "trend_pause_breakout",
    "handle_breakout",
    "stair_step_continuation",
    "rsi_divergence",
    "macd_cross",
    "macd_divergence",
    "rsi_reclaim",
    "rsi_failure_swing_bullish",
    "macd_zero_cross_bullish",
    "macd_histogram_expansion_bullish",
    "trend_acceleration",
    "bollinger_squeeze",
    "bollinger_expansion",
    "volatility_expansion_breakout",
    "band_walk_bullish",
    "volatility_reversal_bullish",
    "volume_dry_up",
    "volume_breakout_confirmation",
    "accumulation_volume",
    "effort_result_divergence_bullish",
    "relative_volume_breakout",
    "volume_follow_through_bullish",
    "selling_climax",
    "volume_trend_confirmation_bullish",
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
    "rectangle_top",
    "broadening_top",
    "ascending_channel_breakdown",
    "rounded_top",
    "diamond_top",
    "bear_flag",
    "rising_channel_breakdown",
    "measured_move_bearish",
    "volatility_contraction_breakdown",
    "pullback_continuation_bearish",
    "momentum_exhaustion",
    "rsi_rejection",
    "rsi_failure_swing_bearish",
    "macd_zero_cross_bearish",
    "macd_histogram_expansion_bearish",
    "trend_deceleration",
    "atr_spike",
    "band_walk_bearish",
    "volatility_reversal_bearish",
    "volume_climax",
    "distribution_volume",
    "effort_result_divergence_bearish",
    "volume_follow_through_bearish",
    "buying_climax",
    "volume_trend_confirmation_bearish",
    "cluster_bearish",
    "distribution",
    "trend_exhaustion",
}

NEUTRAL_PATTERN_SLUGS = {
    "symmetrical_triangle",
    "expanding_triangle",
    "volume_spike",
    "volume_divergence",
    "volatility_compression",
    "atr_compression",
    "atr_release",
    "narrow_range_breakout",
    "mean_reversion_snap",
    "churn_bar",
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
