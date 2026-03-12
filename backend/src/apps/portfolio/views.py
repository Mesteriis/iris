from fastapi import APIRouter, Depends, Query

from src.apps.portfolio.query_services import PortfolioQueryService
from src.apps.portfolio.schemas import PortfolioActionRead, PortfolioPositionRead, PortfolioStateRead
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow

router = APIRouter(tags=["portfolio"])
DB_UOW = Depends(get_uow)


@router.get("/portfolio/positions", response_model=list[PortfolioPositionRead])
async def read_portfolio_positions(
    limit: int = Query(default=100, ge=1, le=500),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[PortfolioPositionRead]:
    items = await PortfolioQueryService(uow.session).list_positions(limit=limit)
    return [PortfolioPositionRead.model_validate(item) for item in items]


@router.get("/portfolio/actions", response_model=list[PortfolioActionRead])
async def read_portfolio_actions(
    limit: int = Query(default=100, ge=1, le=500),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[PortfolioActionRead]:
    items = await PortfolioQueryService(uow.session).list_actions(limit=limit)
    return [PortfolioActionRead.model_validate(item) for item in items]


@router.get("/portfolio/state", response_model=PortfolioStateRead)
async def read_portfolio_state(uow: BaseAsyncUnitOfWork = DB_UOW) -> PortfolioStateRead:
    return PortfolioStateRead.model_validate(await PortfolioQueryService(uow.session).get_state())
