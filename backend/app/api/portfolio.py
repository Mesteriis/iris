from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.portfolio import PortfolioActionRead, PortfolioPositionRead, PortfolioStateRead
from app.services.portfolio_service import get_portfolio_state, list_portfolio_actions, list_portfolio_positions

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/positions", response_model=list[PortfolioPositionRead])
def read_portfolio_positions(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PortfolioPositionRead]:
    return list(list_portfolio_positions(db, limit=limit))


@router.get("/actions", response_model=list[PortfolioActionRead])
def read_portfolio_actions(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PortfolioActionRead]:
    return list(list_portfolio_actions(db, limit=limit))


@router.get("/state", response_model=PortfolioStateRead)
def read_portfolio_state(db: Session = Depends(get_db)) -> PortfolioStateRead:
    return PortfolioStateRead.model_validate(get_portfolio_state(db))
