from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.market_cycle import MarketCycleRead
from app.services.patterns_service import list_market_cycles

router = APIRouter(tags=["market"])


@router.get("/market/cycle", response_model=list[MarketCycleRead])
def read_market_cycles(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[MarketCycleRead]:
    return list(list_market_cycles(db, symbol=symbol, timeframe=timeframe))
