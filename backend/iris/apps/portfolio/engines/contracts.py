from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class PortfolioRebalancePlan:
    action: str
    action_size: float
    position_value: float
    position_size: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    status: str | None


__all__ = ["PortfolioRebalancePlan"]
