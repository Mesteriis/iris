from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.strategy import StrategyPerformanceRead, StrategyRead
from app.services.strategies_service import list_strategies, list_strategy_performance

router = APIRouter(tags=["strategies"])


@router.get("/strategies", response_model=list[StrategyRead])
def read_strategies(
    enabled_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[StrategyRead]:
    return list(list_strategies(db, enabled_only=enabled_only, limit=limit))


@router.get("/strategies/performance", response_model=list[StrategyPerformanceRead])
def read_strategy_performance(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[StrategyPerformanceRead]:
    return list(list_strategy_performance(db, limit=limit))
