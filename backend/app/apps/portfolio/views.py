from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.apps.portfolio.schemas import PortfolioActionRead, PortfolioPositionRead, PortfolioStateRead
from app.apps.portfolio.services import get_portfolio_state, list_portfolio_actions, list_portfolio_positions
from app.core.db.session import get_db

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio/positions", response_model=list[PortfolioPositionRead])
def read_portfolio_positions(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PortfolioPositionRead]:
    return list(list_portfolio_positions(db, limit=limit))


@router.get("/portfolio/actions", response_model=list[PortfolioActionRead])
def read_portfolio_actions(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PortfolioActionRead]:
    return list(list_portfolio_actions(db, limit=limit))


@router.get("/portfolio/state", response_model=PortfolioStateRead)
def read_portfolio_state(db: Session = Depends(get_db)) -> PortfolioStateRead:
    return PortfolioStateRead.model_validate(get_portfolio_state(db))
