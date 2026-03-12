from __future__ import annotations

from datetime import datetime, timezone

from src.apps.patterns.domain.base import PatternDetection
from src.apps.patterns.domain.detectors.continuation import FlagDetector
from src.apps.patterns.domain.detectors.structural import HeadShouldersDetector
from src.apps.patterns.domain.pattern_context import apply_pattern_context, dependencies_satisfied


def test_pattern_dependency_filter() -> None:
    detector = HeadShouldersDetector()
    assert not dependencies_satisfied(
        detector,
        {
            "ema_50": 110.0,
            "ema_200": 100.0,
            "current_volume": None,
            "average_volume_20": None,
        },
    )
    assert dependencies_satisfied(
        detector,
        {
            "ema_50": 110.0,
            "ema_200": 100.0,
            "current_volume": 1000.0,
            "average_volume_20": 800.0,
        },
    )


def test_pattern_context_filters_against_wrong_regime() -> None:
    detector = FlagDetector("bull_flag", "bull")
    detection = PatternDetection(
        slug="bull_flag",
        signal_type="pattern_bull_flag",
        confidence=0.7,
        candle_timestamp=datetime(2026, 3, 11, 14, 0, tzinfo=timezone.utc),
        category="continuation",
    )
    adjusted = apply_pattern_context(
        detection=detection,
        detector=detector,
        indicators={
            "price_current": 100.0,
            "ema_50": 102.0,
            "ema_200": 99.0,
            "current_volume": 1500.0,
            "average_volume_20": 1200.0,
        },
        regime="bear_trend",
    )
    assert adjusted is None


def test_pattern_context_boosts_aligned_regime() -> None:
    detector = FlagDetector("bull_flag", "bull")
    detection = PatternDetection(
        slug="bull_flag",
        signal_type="pattern_bull_flag",
        confidence=0.7,
        candle_timestamp=datetime(2026, 3, 11, 14, 0, tzinfo=timezone.utc),
        category="continuation",
    )
    adjusted = apply_pattern_context(
        detection=detection,
        detector=detector,
        indicators={
            "price_current": 100.0,
            "ema_50": 105.0,
            "ema_200": 98.0,
            "current_volume": 1500.0,
            "average_volume_20": 1200.0,
        },
        regime="bull_trend",
    )
    assert adjusted is not None
    assert adjusted.confidence > detection.confidence
    assert adjusted.attributes["regime"] == "bull_trend"
