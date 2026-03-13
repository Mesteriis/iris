from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder

from src.apps.portfolio.api.contracts import PortfolioActionRead, PortfolioPositionRead, PortfolioStateRead
from src.core.http.analytics import analytical_metadata


def portfolio_position_read(item: Any) -> PortfolioPositionRead:
    return PortfolioPositionRead.model_validate(item)


def portfolio_action_read(item: Any) -> PortfolioActionRead:
    return PortfolioActionRead.model_validate(item)


def portfolio_state_read(item: Any) -> PortfolioStateRead:
    payload = jsonable_encoder(item)
    return PortfolioStateRead.model_validate(
        {
            **payload,
            **analytical_metadata(
                source_updated_at=payload.get("updated_at"),
                consistency="cached",
                freshness_class="near_real_time",
            ),
        }
    )


__all__ = ["portfolio_action_read", "portfolio_position_read", "portfolio_state_read"]
