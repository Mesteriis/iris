from fastapi import APIRouter, Query, Request, Response

from iris.apps.portfolio.api.contracts import PortfolioActionRead, PortfolioPositionRead, PortfolioStateRead
from iris.apps.portfolio.api.deps import PortfolioQueryDep
from iris.apps.portfolio.api.presenters import (
    portfolio_action_read,
    portfolio_position_read,
    portfolio_state_read,
)
from iris.core.http.cache import PRIVATE_NEAR_REALTIME_CACHE, apply_conditional_cache, cache_not_modified_responses

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


@router.get(
    "/portfolio/state",
    response_model=PortfolioStateRead,
    summary="Read portfolio state",
    responses=cache_not_modified_responses(),
)
async def read_portfolio_state(
    request: Request,
    response: Response,
    service: PortfolioQueryDep,
) -> PortfolioStateRead | Response:
    payload = portfolio_state_read(await service.get_state())
    if not_modified := apply_conditional_cache(
        request=request,
        response=response,
        payload=payload,
        policy=PRIVATE_NEAR_REALTIME_CACHE,
        generated_at=payload.generated_at,
        staleness_ms=payload.staleness_ms,
    ):
        return not_modified
    return payload
