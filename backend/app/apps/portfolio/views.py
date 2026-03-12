from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.portfolio.schemas import PortfolioActionRead, PortfolioPositionRead, PortfolioStateRead
from app.apps.portfolio.services import (
    get_portfolio_state_async,
    list_portfolio_actions_async,
    list_portfolio_positions_async,
)
from app.core.db.session import get_db

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio/positions", response_model=list[PortfolioPositionRead])
async def read_portfolio_positions(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[PortfolioPositionRead]:
    return list(await list_portfolio_positions_async(db, limit=limit))


@router.get("/portfolio/actions", response_model=list[PortfolioActionRead])
async def read_portfolio_actions(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[PortfolioActionRead]:
    return list(await list_portfolio_actions_async(db, limit=limit))


@router.get("/portfolio/state", response_model=PortfolioStateRead)
async def read_portfolio_state(db: AsyncSession = Depends(get_db)) -> PortfolioStateRead:
    return PortfolioStateRead.model_validate(await get_portfolio_state_async(db))
