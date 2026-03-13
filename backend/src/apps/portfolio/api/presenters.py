from __future__ import annotations

from typing import Any

from src.apps.portfolio.api.contracts import PortfolioActionRead, PortfolioPositionRead, PortfolioStateRead


def portfolio_position_read(item: Any) -> PortfolioPositionRead:
    return PortfolioPositionRead.model_validate(item)


def portfolio_action_read(item: Any) -> PortfolioActionRead:
    return PortfolioActionRead.model_validate(item)


def portfolio_state_read(item: Any) -> PortfolioStateRead:
    return PortfolioStateRead.model_validate(item)


__all__ = ["portfolio_action_read", "portfolio_position_read", "portfolio_state_read"]
