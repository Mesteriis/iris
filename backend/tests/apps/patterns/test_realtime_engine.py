import pytest
from iris.apps.patterns.engines import (
    PatternCoinMetricsSnapshot,
    PatternCycleEngineInput,
    PatternRuntimeSignalSnapshot,
    build_pattern_cluster_specs,
    build_pattern_hierarchy_specs,
    compute_pattern_market_cycle,
)


@pytest.fixture(autouse=True)
def isolated_event_stream() -> None:
    yield


def test_pattern_realtime_engine_builds_bullish_cluster_specs() -> None:
    specs = build_pattern_cluster_specs(
        signals=(
            PatternRuntimeSignalSnapshot(signal_type="pattern_breakout_retest", confidence=0.81),
            PatternRuntimeSignalSnapshot(signal_type="pattern_volume_spike", confidence=0.88),
        ),
        metrics=PatternCoinMetricsSnapshot(
            trend_score=72,
            market_regime="bull_trend",
            resolved_regime="bull_trend",
            volatility=0.8,
            price_current=100.0,
        ),
    )

    assert specs
    assert specs[0].signal_type == "pattern_cluster_bullish"
    assert specs[0].market_regime == "bull_trend"
    assert specs[0].confidence > 0.9


def test_pattern_realtime_engine_builds_bearish_hierarchy_specs() -> None:
    specs = build_pattern_hierarchy_specs(
        signals=(
            PatternRuntimeSignalSnapshot(signal_type="pattern_bear_flag", confidence=0.82),
            PatternRuntimeSignalSnapshot(signal_type="pattern_rising_channel_breakdown", confidence=0.8),
            PatternRuntimeSignalSnapshot(signal_type="pattern_volume_climax", confidence=0.9),
            PatternRuntimeSignalSnapshot(signal_type="pattern_momentum_exhaustion", confidence=0.86),
            PatternRuntimeSignalSnapshot(signal_type="pattern_cluster_bearish", confidence=0.92),
        ),
        has_cluster_signals=True,
        metrics=PatternCoinMetricsSnapshot(
            trend_score=32,
            market_regime="bear_trend",
            resolved_regime="bear_trend",
            volatility=5.0,
            price_current=100.0,
        ),
    )

    assert {spec.signal_type for spec in specs} == {
        "pattern_hierarchy_distribution",
        "pattern_hierarchy_trend_exhaustion",
    }


def test_pattern_realtime_engine_computes_markup_cycle() -> None:
    cycle = compute_pattern_market_cycle(
        PatternCycleEngineInput(
            trend_score=78,
            regime="bull_trend",
            volatility=1.2,
            price_current=100.0,
            pattern_density=2,
            cluster_frequency=1,
            sector_strength=0.91,
            capital_flow=0.62,
        )
    )

    assert cycle.cycle_phase == "MARKUP"
    assert cycle.confidence == 0.84
