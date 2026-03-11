from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.market_cycle import MarketCycleRead
from app.schemas.market_flow import MarketFlowRead
from app.schemas.market_radar import MarketRadarRead
from app.services.market_flow_service import get_market_flow
from app.services.market_radar_service import get_market_radar
from app.services.patterns_service import list_market_cycles

router = APIRouter(tags=["market"])


@router.get("/market/cycle", response_model=list[MarketCycleRead])
def read_market_cycles(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[MarketCycleRead]:
    return list(list_market_cycles(db, symbol=symbol, timeframe=timeframe))


@router.get("/market/radar", response_model=MarketRadarRead)
def read_market_radar(
    limit: int = Query(default=8, ge=1, le=24),
    db: Session = Depends(get_db),
) -> MarketRadarRead:
    return get_market_radar(db, limit=limit)


@router.get("/market/flow", response_model=MarketFlowRead)
def read_market_flow(
    limit: int = Query(default=8, ge=1, le=24),
    timeframe: int = Query(default=60, ge=15, le=1440),
    db: Session = Depends(get_db),
) -> MarketFlowRead:
    return get_market_flow(db, limit=limit, timeframe=timeframe)
