from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.apps.indicators.schemas import CoinMetricsRead, MarketFlowRead, MarketRadarRead
from app.apps.patterns.schemas import MarketCycleRead
from app.apps.indicators.services import get_market_flow, get_market_radar, list_coin_metrics
from app.apps.patterns.services import list_market_cycles
from app.core.db.session import get_db

router = APIRouter(tags=["indicators"])


@router.get("/coins/metrics", response_model=list[CoinMetricsRead], tags=["metrics"])
def read_coin_metrics(db: Session = Depends(get_db)) -> list[CoinMetricsRead]:
    return list(list_coin_metrics(db))


@router.get("/market/cycle", response_model=list[MarketCycleRead], tags=["market"])
def read_market_cycles(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[MarketCycleRead]:
    return list(list_market_cycles(db, symbol=symbol, timeframe=timeframe))


@router.get("/market/radar", response_model=MarketRadarRead, tags=["market"])
def read_market_radar(
    limit: int = Query(default=8, ge=1, le=24),
    db: Session = Depends(get_db),
) -> MarketRadarRead:
    return get_market_radar(db, limit=limit)


@router.get("/market/flow", response_model=MarketFlowRead, tags=["market"])
def read_market_flow(
    limit: int = Query(default=8, ge=1, le=24),
    timeframe: int = Query(default=60, ge=15, le=1440),
    db: Session = Depends(get_db),
) -> MarketFlowRead:
    return get_market_flow(db, limit=limit, timeframe=timeframe)
