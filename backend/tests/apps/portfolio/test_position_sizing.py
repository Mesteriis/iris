from __future__ import annotations

from src.apps.portfolio.support import calculate_position_size, calculate_stops


def test_position_sizing_scales_with_confidence_and_regime() -> None:
    bullish = calculate_position_size(
        total_capital=100_000.0,
        available_capital=100_000.0,
        decision_confidence=0.8,
        regime="bull_trend",
        price_current=100.0,
        atr_14=2.0,
    )
    bearish = calculate_position_size(
        total_capital=100_000.0,
        available_capital=100_000.0,
        decision_confidence=0.8,
        regime="bear_trend",
        price_current=100.0,
        atr_14=2.0,
    )

    assert bullish["position_value"] > bearish["position_value"]
    assert bullish["position_value"] <= 5_000.0


def test_stop_calculation_uses_atr_multipliers() -> None:
    stops = calculate_stops(entry_price=100.0, atr=2.5)

    assert stops.stop_loss == 95.0
    assert stops.take_profit == 107.5
