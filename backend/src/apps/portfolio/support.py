from __future__ import annotations

from dataclasses import dataclass

from src.core.settings import get_settings

PORTFOLIO_ACTIONS = {
    "OPEN_POSITION",
    "CLOSE_POSITION",
    "REDUCE_POSITION",
    "INCREASE_POSITION",
    "HOLD_POSITION",
}
SIMULATION_EXCHANGE = "portfolio_engine"
DEFAULT_PORTFOLIO_TIMEFRAME = 1440


@dataclass(slots=True, frozen=True)
class StopRead:
    stop_loss: float | None
    take_profit: float | None


def clamp_portfolio_value(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def calculate_stops(*, entry_price: float | None, atr: float | None) -> StopRead:
    settings = get_settings()
    if not entry_price or entry_price <= 0 or atr is None or atr <= 0:
        return StopRead(stop_loss=None, take_profit=None)
    stop_loss = max(entry_price - atr * settings.portfolio_stop_atr_multiplier, 0.0)
    take_profit = entry_price + atr * settings.portfolio_take_profit_atr_multiplier
    return StopRead(stop_loss=stop_loss, take_profit=take_profit)


def calculate_position_size(
    *,
    total_capital: float,
    available_capital: float,
    decision_confidence: float,
    regime: str | None,
    price_current: float | None,
    atr_14: float | None,
) -> dict[str, float]:
    settings = get_settings()
    base_size = total_capital * settings.portfolio_max_position_size
    regime_factor = 1.0
    if regime == "bull_trend":
        regime_factor = 1.15
    elif regime == "bear_trend":
        regime_factor = 0.75
    elif regime == "sideways_range":
        regime_factor = 0.85
    elif regime == "high_volatility":
        regime_factor = 0.95
    volatility_adjustment = 1.0
    if price_current and price_current > 0 and atr_14 is not None:
        volatility_adjustment = clamp_portfolio_value(1.0 - float(atr_14) / float(price_current), 0.55, 1.05)
    raw_value = base_size * clamp_portfolio_value(decision_confidence, 0.0, 1.0) * regime_factor * volatility_adjustment
    capped_value = min(raw_value, total_capital * settings.portfolio_max_position_size, available_capital)
    return {
        "base_size": base_size,
        "regime_factor": regime_factor,
        "volatility_adjustment": volatility_adjustment,
        "position_value": max(capped_value, 0.0),
    }


__all__ = [
    "DEFAULT_PORTFOLIO_TIMEFRAME",
    "PORTFOLIO_ACTIONS",
    "SIMULATION_EXCHANGE",
    "StopRead",
    "calculate_position_size",
    "calculate_stops",
    "clamp_portfolio_value",
]
