from __future__ import annotations

from fastapi import APIRouter, Query

from src.apps.portfolio.api.contracts import PortfolioActionRead, PortfolioPositionRead, PortfolioStateRead
from src.apps.portfolio.api.deps import PortfolioQueryDep
from src.apps.portfolio.api.presenters import (
    portfolio_action_read,
    portfolio_position_read,
    portfolio_state_read,
)

router = APIRouter(tags=["portfolio:read"])


@router.get("/portfolio/positions", response_model=list[PortfolioPositionRead], summary="List portfolio positions")
async def read_portfolio_positions(
    service: PortfolioQueryDep,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PortfolioPositionRead]:
    return [portfolio_position_read(item) for item in await service.list_positions(limit=limit)]


@router.get("/portfolio/actions", response_model=list[PortfolioActionRead], summary="List portfolio actions")
async def read_portfolio_actions(
    service: PortfolioQueryDep,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PortfolioActionRead]:
    return [portfolio_action_read(item) for item in await service.list_actions(limit=limit)]


@router.get("/portfolio/state", response_model=PortfolioStateRead, summary="Read portfolio state")
async def read_portfolio_state(service: PortfolioQueryDep) -> PortfolioStateRead:
    return portfolio_state_read(await service.get_state())
