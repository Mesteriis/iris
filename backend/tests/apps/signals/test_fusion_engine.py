from datetime import UTC, datetime, timedelta

from src.apps.signals.engines import (
    SignalFusionInput,
    SignalFusionNewsImpactInput,
    SignalFusionSignalInput,
    SignalSuccessRate,
    run_signal_fusion,
)


def test_signal_fusion_engine_returns_explainable_buy_result() -> None:
    reference_time = datetime(2026, 3, 11, 14, 0, tzinfo=UTC)
    result = run_signal_fusion(
        SignalFusionInput(
            signals=(
                SignalFusionSignalInput(
                    signal_type="pattern_bull_flag",
                    confidence=0.82,
                    priority_score=1.0,
                    context_score=1.0,
                    regime_alignment=1.0,
                    candle_timestamp=reference_time - timedelta(minutes=15),
                ),
                SignalFusionSignalInput(
                    signal_type="pattern_breakout_retest",
                    confidence=0.77,
                    priority_score=1.0,
                    context_score=1.0,
                    regime_alignment=1.0,
                    candle_timestamp=reference_time,
                ),
            ),
            regime="bull_trend",
            success_rates=(
                SignalSuccessRate(pattern_slug="bull_flag", market_regime="all", success_rate=0.72),
                SignalSuccessRate(pattern_slug="breakout_retest", market_regime="all", success_rate=0.69),
            ),
            bullish_alignment=1.08,
            bearish_alignment=0.94,
            news_impact=SignalFusionNewsImpactInput(
                item_count=1,
                bullish_score=0.18,
                bearish_score=0.0,
                latest_timestamp=reference_time + timedelta(minutes=5),
            ),
        )
    )

    assert result is not None
    assert result.decision == "BUY"
    assert result.news_item_count == 1
    assert result.explainability is not None
    assert result.explainability.policy_path == "signal_fusion/v1/news_adjusted"
    assert "news_impact_applied" in result.explainability.threshold_crossings
    assert result.explainability.dominant_factors


def test_signal_fusion_engine_is_deterministic_for_identical_input() -> None:
    fusion_input = SignalFusionInput(
        signals=(
            SignalFusionSignalInput(
                signal_type="pattern_bull_flag",
                confidence=0.8,
                priority_score=1.0,
                context_score=1.0,
                regime_alignment=1.0,
                candle_timestamp=datetime(2026, 3, 11, 13, 45, tzinfo=UTC),
            ),
            SignalFusionSignalInput(
                signal_type="pattern_head_shoulders",
                confidence=0.74,
                priority_score=1.0,
                context_score=1.0,
                regime_alignment=1.0,
                candle_timestamp=datetime(2026, 3, 11, 13, 30, tzinfo=UTC),
            ),
        ),
        regime="bull_trend",
        success_rates=(SignalSuccessRate(pattern_slug="bull_flag", market_regime="all", success_rate=0.72),),
        bullish_alignment=1.0,
        bearish_alignment=1.0,
    )

    assert run_signal_fusion(fusion_input) == run_signal_fusion(fusion_input)
