from fastapi import APIRouter, Depends, Query

from src.apps.indicators.query_services import IndicatorQueryService
from src.apps.indicators.schemas import CoinMetricsRead, MarketFlowRead, MarketRadarRead
from src.apps.patterns.query_services import PatternQueryService
from src.apps.patterns.schemas import MarketCycleRead
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow

router = APIRouter(tags=["indicators"])
DB_UOW = Depends(get_uow)


@router.get("/coins/metrics", response_model=list[CoinMetricsRead], tags=["metrics"])
async def read_coin_metrics(uow: BaseAsyncUnitOfWork = DB_UOW) -> list[CoinMetricsRead]:
    items = await IndicatorQueryService(uow.session).list_coin_metrics()
    return [CoinMetricsRead.model_validate(item) for item in items]


@router.get("/market/cycle", response_model=list[MarketCycleRead], tags=["market"])
async def read_market_cycles(
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[MarketCycleRead]:
    items = await PatternQueryService(uow.session).list_market_cycles(symbol=symbol, timeframe=timeframe)
    return [MarketCycleRead.model_validate(item) for item in items]


@router.get("/market/radar", response_model=MarketRadarRead, tags=["market"])
async def read_market_radar(
    limit: int = Query(default=8, ge=1, le=24),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketRadarRead:
    return MarketRadarRead.model_validate(await IndicatorQueryService(uow.session).get_market_radar(limit=limit))


@router.get("/market/flow", response_model=MarketFlowRead, tags=["market"])
async def read_market_flow(
    limit: int = Query(default=8, ge=1, le=24),
    timeframe: int = Query(default=60, ge=15, le=1440),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> MarketFlowRead:
    return MarketFlowRead.model_validate(
        await IndicatorQueryService(uow.session).get_market_flow(limit=limit, timeframe=timeframe)
    )
