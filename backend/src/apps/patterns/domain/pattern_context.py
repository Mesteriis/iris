from __future__ import annotations

from src.apps.patterns.domain.base import PatternDetection, PatternDetector
from src.apps.patterns.domain.regime import detect_market_regime
from src.apps.patterns.domain.semantics import pattern_bias
from src.apps.patterns.domain.utils import clamp

TREND_DEPENDENCY_SLUGS = {
    "head_shoulders",
    "inverse_head_shoulders",
    "double_top",
    "double_bottom",
    "triple_top",
    "triple_bottom",
    "bull_flag",
    "bear_flag",
    "pennant",
    "cup_and_handle",
    "breakout_retest",
    "consolidation_breakout",
}
VOLUME_DEPENDENCY_SLUGS = {
    "head_shoulders",
    "inverse_head_shoulders",
    "cup_and_handle",
    "breakout_retest",
    "volume_spike",
    "volume_climax",
    "volume_divergence",
}
REVERSAL_SLUGS = {
    "head_shoulders",
    "inverse_head_shoulders",
    "double_top",
    "double_bottom",
    "triple_top",
    "triple_bottom",
    "rounded_top",
    "rounded_bottom",
    "diamond_top",
    "diamond_bottom",
    "momentum_exhaustion",
    "mean_reversion_snap",
    "volatility_reversal_bullish",
    "volatility_reversal_bearish",
    "volume_divergence",
    "volume_climax",
    "buying_climax",
    "selling_climax",
}
MEAN_REVERSION_SLUGS = {
    "rsi_divergence",
    "macd_divergence",
    "mean_reversion_snap",
    "volume_divergence",
    "rsi_failure_swing_bullish",
    "rsi_failure_swing_bearish",
}
VOLATILITY_BREAKOUT_SLUGS = {
    "bollinger_squeeze",
    "bollinger_expansion",
    "atr_spike",
    "volatility_expansion_breakout",
    "narrow_range_breakout",
    "atr_release",
}


def _additional_dependencies(detector: PatternDetector) -> set[str]:
    required: set[str] = set(detector.required_indicators)
    if detector.category in {"continuation", "structural"} or detector.slug in TREND_DEPENDENCY_SLUGS:
        required.add("trend")
    if detector.category == "volume" or detector.slug in VOLUME_DEPENDENCY_SLUGS:
        required.add("volume")
    return required


def dependencies_satisfied(detector: PatternDetector, indicators: dict[str, float | None]) -> bool:
    for dependency in _additional_dependencies(detector):
        if dependency == "trend":
            if indicators.get("ema_50") is None or (
                indicators.get("ema_200") is None and indicators.get("sma_200") is None
            ):
                return False
            continue
        if dependency == "volume":
            if indicators.get("current_volume") is None or indicators.get("average_volume_20") is None:
                return False
            continue
        if indicators.get(dependency) is None:
            return False
    return True


def resolve_pattern_regime(
    *,
    regime: str | None,
    indicators: dict[str, float | None],
) -> str:
    if regime:
        return regime
    detected_regime, _ = detect_market_regime(indicators)
    return detected_regime


def regime_weight(
    *,
    detection: PatternDetection,
    detector: PatternDetector,
    regime: str,
) -> float:
    bias = pattern_bias(detection.slug, fallback_price_delta=detection.confidence - 0.5)
    is_bullish = bias > 0
    if detector.category == "continuation":
        if regime == "bull_trend":
            return 1.18 if is_bullish else 0.58
        if regime == "bear_trend":
            return 1.18 if not is_bullish else 0.58
        if regime == "sideways_range":
            return 0.68
        if regime == "high_volatility":
            return 1.05
        return 0.82
    if detection.slug in REVERSAL_SLUGS or detector.category == "structural":
        if regime == "bull_trend":
            return 1.14 if not is_bullish else 0.72
        if regime == "bear_trend":
            return 1.14 if is_bullish else 0.72
        if regime == "sideways_range":
            return 0.95
        if regime == "high_volatility":
            return 1.0
        return 0.85
    if detection.slug in MEAN_REVERSION_SLUGS:
        if regime in {"sideways_range", "low_volatility"}:
            return 1.14
        if regime in {"bull_trend", "bear_trend"}:
            return 0.7
        return 0.88
    if detector.category == "volatility" or detection.slug in VOLATILITY_BREAKOUT_SLUGS:
        if regime == "high_volatility":
            return 1.16
        if regime == "low_volatility":
            return 1.08 if detection.slug in {"bollinger_squeeze", "narrow_range_breakout"} else 0.76
        return 0.9
    if detector.category == "volume":
        if regime in {"bull_trend", "bear_trend", "high_volatility"}:
            return 1.06
        return 0.94
    return 1.0


def apply_pattern_context(
    *,
    detection: PatternDetection,
    detector: PatternDetector,
    indicators: dict[str, float | None],
    regime: str | None,
) -> PatternDetection | None:
    effective_regime = resolve_pattern_regime(regime=regime, indicators=indicators)
    weight = regime_weight(
        detection=detection,
        detector=detector,
        regime=effective_regime,
    )
    if weight < 0.6:
        return None
    return PatternDetection(
        slug=detection.slug,
        signal_type=detection.signal_type,
        confidence=clamp(detection.confidence * weight, 0.35, 0.99),
        candle_timestamp=detection.candle_timestamp,
        category=detection.category,
        attributes={
            **detection.attributes,
            "regime": effective_regime,
            "regime_weight": round(weight, 4),
        },
    )
