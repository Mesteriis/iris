from datetime import UTC, datetime, timezone

import pytest
import src.apps.patterns.domain.pattern_context as pattern_context_module
from src.apps.patterns.domain.base import PatternDetection, PatternDetector
from src.apps.patterns.domain.pattern_context import (
    _additional_dependencies,
    apply_pattern_context,
    dependencies_satisfied,
    regime_weight,
    resolve_pattern_regime,
)


class _Detector(PatternDetector):
    def __init__(self, *, slug: str, category: str, required_indicators: list[str] | None = None) -> None:
        self.slug = slug
        self.category = category
        self.required_indicators = required_indicators or []

    def detect(self, candles, indicators):
        return []


def _detection(slug: str, category: str = "generic", confidence: float = 0.8) -> PatternDetection:
    return PatternDetection(
        slug=slug,
        signal_type=f"pattern_{slug}",
        confidence=confidence,
        candle_timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=UTC),
        category=category,
        attributes={"origin": "test"},
    )


def test_pattern_context_dependencies_regime_weights_and_application(monkeypatch) -> None:
    continuation = _Detector(slug="bull_flag", category="continuation", required_indicators=["rsi_14"])
    volume = _Detector(slug="volume_spike", category="volume")
    custom = _Detector(slug="custom", category="generic", required_indicators=["macd"])

    assert _additional_dependencies(continuation) == {"trend", "rsi_14"}
    assert _additional_dependencies(volume) == {"volume"}
    assert _additional_dependencies(custom) == {"macd"}

    assert not dependencies_satisfied(continuation, {"rsi_14": 60.0, "ema_200": 100.0})
    assert not dependencies_satisfied(continuation, {"rsi_14": 60.0, "ema_50": 105.0})
    assert not dependencies_satisfied(volume, {"current_volume": 1000.0})
    assert not dependencies_satisfied(custom, {})
    assert dependencies_satisfied(
        continuation,
        {
            "rsi_14": 60.0,
            "ema_50": 105.0,
            "ema_200": 100.0,
            "current_volume": 2000.0,
            "average_volume_20": 1000.0,
        },
    )

    monkeypatch.setattr(pattern_context_module, "detect_market_regime", lambda indicators: ("high_volatility", 0.73))
    assert resolve_pattern_regime(regime="bull_trend", indicators={}) == "bull_trend"
    assert resolve_pattern_regime(regime=None, indicators={"ema_50": 105.0}) == "high_volatility"

    bullish_detection = _detection("bull_flag", category="continuation", confidence=0.82)
    bearish_detection = _detection("bear_flag", category="continuation", confidence=0.82)
    continuation_detector = _Detector(slug="bull_flag", category="continuation")
    assert regime_weight(detection=bullish_detection, detector=continuation_detector, regime="bull_trend") == 1.18
    assert regime_weight(detection=bearish_detection, detector=continuation_detector, regime="bull_trend") == 0.58
    assert regime_weight(detection=bullish_detection, detector=continuation_detector, regime="bear_trend") == 0.58
    assert regime_weight(detection=bullish_detection, detector=continuation_detector, regime="sideways_range") == 0.68
    assert regime_weight(detection=bullish_detection, detector=continuation_detector, regime="high_volatility") == 1.05
    assert regime_weight(detection=bullish_detection, detector=continuation_detector, regime="unknown") == 0.82

    structural_detector = _Detector(slug="head_shoulders", category="structural")
    bearish_reversal = _detection("head_shoulders", category="structural", confidence=0.84)
    bullish_reversal = _detection("inverse_head_shoulders", category="structural", confidence=0.84)
    assert regime_weight(detection=bearish_reversal, detector=structural_detector, regime="bull_trend") == 1.14
    assert regime_weight(detection=bullish_reversal, detector=structural_detector, regime="bull_trend") == 0.72
    assert regime_weight(detection=bullish_reversal, detector=structural_detector, regime="bear_trend") == 1.14
    assert regime_weight(detection=bullish_reversal, detector=structural_detector, regime="sideways_range") == 0.95
    assert regime_weight(detection=bullish_reversal, detector=structural_detector, regime="high_volatility") == 1.0
    assert regime_weight(detection=bullish_reversal, detector=structural_detector, regime="unknown") == 0.85

    mean_reversion_detector = _Detector(slug="rsi_divergence", category="momentum")
    mean_reversion_detection = _detection("rsi_divergence", confidence=0.74)
    assert regime_weight(detection=mean_reversion_detection, detector=mean_reversion_detector, regime="sideways_range") == 1.14
    assert regime_weight(detection=mean_reversion_detection, detector=mean_reversion_detector, regime="low_volatility") == 1.14
    assert regime_weight(detection=mean_reversion_detection, detector=mean_reversion_detector, regime="bull_trend") == 0.7
    assert regime_weight(detection=mean_reversion_detection, detector=mean_reversion_detector, regime="unknown") == 0.88

    volatility_detector = _Detector(slug="bollinger_squeeze", category="volatility")
    squeeze_detection = _detection("bollinger_squeeze", category="volatility")
    atr_detection = _detection("atr_spike", category="volatility")
    assert regime_weight(detection=squeeze_detection, detector=volatility_detector, regime="high_volatility") == 1.16
    assert regime_weight(detection=squeeze_detection, detector=volatility_detector, regime="low_volatility") == 1.08
    assert regime_weight(detection=atr_detection, detector=volatility_detector, regime="low_volatility") == 0.76
    assert regime_weight(detection=atr_detection, detector=volatility_detector, regime="unknown") == 0.9

    volume_detector = _Detector(slug="volume_spike", category="volume")
    volume_detection = _detection("volume_spike", category="volume")
    assert regime_weight(detection=volume_detection, detector=volume_detector, regime="bull_trend") == 1.06
    assert regime_weight(detection=volume_detection, detector=volume_detector, regime="sideways_range") == 0.94

    generic_detector = _Detector(slug="custom", category="generic")
    assert regime_weight(detection=_detection("custom"), detector=generic_detector, regime="anything") == 1.0

    assert apply_pattern_context(
        detection=bearish_detection,
        detector=continuation_detector,
        indicators={"ema_50": 105.0, "ema_200": 100.0},
        regime="bull_trend",
    ) is None

    contextual = apply_pattern_context(
        detection=_detection("bull_flag", category="continuation", confidence=0.92),
        detector=continuation_detector,
        indicators={"ema_50": 105.0, "ema_200": 100.0},
        regime=None,
    )
    assert contextual is not None
    assert contextual.attributes["origin"] == "test"
    assert contextual.attributes["regime"] == "high_volatility"
    assert contextual.attributes["regime_weight"] == 1.05
    assert 0.35 <= contextual.confidence <= 0.99
