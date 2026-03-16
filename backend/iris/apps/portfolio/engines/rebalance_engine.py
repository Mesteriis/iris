from iris.apps.portfolio.engines.contracts import PortfolioRebalancePlan
from iris.apps.portfolio.support import calculate_stops


def build_rebalance_plan(
    *,
    current_value: float,
    target_value: float,
    entry_price: float,
    atr_14: float | None,
) -> PortfolioRebalancePlan:
    stops = calculate_stops(entry_price=entry_price, atr=atr_14)
    normalized_entry_price = max(entry_price, 1e-9)
    if target_value <= 0:
        return PortfolioRebalancePlan(
            action="CLOSE_POSITION",
            action_size=current_value,
            position_value=0.0,
            position_size=0.0,
            entry_price=entry_price,
            stop_loss=None,
            take_profit=None,
            status="closed",
        )
    if current_value <= 0:
        return PortfolioRebalancePlan(
            action="OPEN_POSITION",
            action_size=target_value,
            position_value=target_value,
            position_size=target_value / normalized_entry_price,
            entry_price=entry_price,
            stop_loss=stops.stop_loss,
            take_profit=stops.take_profit,
            status="open",
        )

    delta = target_value - current_value
    action = "HOLD_POSITION"
    action_size = 0.0
    status: str | None = None
    if delta > current_value * 0.1:
        action = "INCREASE_POSITION"
        action_size = delta
    elif delta < -(current_value * 0.1):
        action = "REDUCE_POSITION"
        action_size = abs(delta)
        status = "partial"

    return PortfolioRebalancePlan(
        action=action,
        action_size=action_size,
        position_value=target_value,
        position_size=target_value / normalized_entry_price,
        entry_price=entry_price,
        stop_loss=stops.stop_loss,
        take_profit=stops.take_profit,
        status=status,
    )


__all__ = ["build_rebalance_plan"]
