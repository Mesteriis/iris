from fastapi import APIRouter, Query, Request, Response

from src.apps.indicators.api.contracts import CoinMetricsRead, MarketCycleRead, MarketFlowRead, MarketRadarRead
from src.apps.indicators.api.deps import IndicatorReadDep
from src.apps.indicators.api.presenters import (
    coin_metrics_read,
    market_cycle_read,
    market_flow_read,
    market_radar_read,
)
from src.core.http.cache import PUBLIC_NEAR_REALTIME_CACHE, apply_conditional_cache, cache_not_modified_responses

router = APIRouter(tags=["indicators:read"])


@router.get("/coins/metrics", response_model=list[CoinMetricsRead], summary="List coin metrics")
async def read_coin_metrics(service: IndicatorReadDep) -> list[CoinMetricsRead]:
    return [coin_metrics_read(item) for item in await service.list_coin_metrics()]


@router.get("/market/cycle", response_model=list[MarketCycleRead], summary="Read market cycles")
async def read_market_cycles(
    service: IndicatorReadDep,
    symbol: str | None = Query(default=None),
    timeframe: int | None = Query(default=None),
) -> list[MarketCycleRead]:
    items = await service.list_market_cycles(symbol=symbol, timeframe=timeframe)
    return [market_cycle_read(item) for item in items]


@router.get(
    "/market/radar",
    response_model=MarketRadarRead,
    summary="Read market radar",
    responses=cache_not_modified_responses(),
)
async def read_market_radar(
    request: Request,
    response: Response,
    service: IndicatorReadDep,
    limit: int = Query(default=8, ge=1, le=24),
) -> MarketRadarRead | Response:
    payload = market_radar_read(await service.get_market_radar(limit=limit))
    if not_modified := apply_conditional_cache(
        request=request,
        response=response,
        payload=payload,
        policy=PUBLIC_NEAR_REALTIME_CACHE,
        generated_at=payload.generated_at,
        staleness_ms=payload.staleness_ms,
    ):
        return not_modified
    return payload


@router.get(
    "/market/flow",
    response_model=MarketFlowRead,
    summary="Read market flow",
    responses=cache_not_modified_responses(),
)
async def read_market_flow(
    request: Request,
    response: Response,
    service: IndicatorReadDep,
    limit: int = Query(default=8, ge=1, le=24),
    timeframe: int = Query(default=60, ge=15, le=1440),
) -> MarketFlowRead | Response:
    payload = market_flow_read(await service.get_market_flow(limit=limit, timeframe=timeframe))
    if not_modified := apply_conditional_cache(
        request=request,
        response=response,
        payload=payload,
        policy=PUBLIC_NEAR_REALTIME_CACHE,
        generated_at=payload.generated_at,
        staleness_ms=payload.staleness_ms,
    ):
        return not_modified
    return payload
