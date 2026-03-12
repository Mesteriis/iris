from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.indicators.schemas import CoinMetricsRead, MarketFlowRead, MarketRadarRead
from app.apps.patterns.schemas import MarketCycleRead
from app.apps.indicators.services import get_market_flow_async, get_market_radar_async, list_coin_metrics_async
from app.apps.patterns.services import list_market_cycles_async
from app.core.db.session import get_db

router = APIRouter(tags=["indicators"])


@router.get("/coins/metrics", response_model=list[CoinMetricsRead], tags=["metrics"])
async def read_coin_metrics(db: AsyncSession = Depends(get_db)) -> list[CoinMetricsRead]:
    return list(await list_coin_metrics_async(db))


@router.get("/market/cycle", response_model=list[MarketCycleRead], tags=["market"])
async def read_market_cycles(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[MarketCycleRead]:
    return list(await list_market_cycles_async(db, symbol=symbol, timeframe=timeframe))


@router.get("/market/radar", response_model=MarketRadarRead, tags=["market"])
async def read_market_radar(
    limit: int = Query(default=8, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
) -> MarketRadarRead:
    return await get_market_radar_async(db, limit=limit)


@router.get("/market/flow", response_model=MarketFlowRead, tags=["market"])
async def read_market_flow(
    limit: int = Query(default=8, ge=1, le=24),
    timeframe: int = Query(default=60, ge=15, le=1440),
    db: AsyncSession = Depends(get_db),
) -> MarketFlowRead:
    return await get_market_flow_async(db, limit=limit, timeframe=timeframe)
