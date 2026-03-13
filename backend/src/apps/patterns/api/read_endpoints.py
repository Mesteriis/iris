from __future__ import annotations

from fastapi import APIRouter, Query

from src.apps.patterns.api.contracts import (
    CoinRegimeRead,
    DiscoveredPatternRead,
    PatternFeatureRead,
    PatternRead,
    SectorMetricsResponse,
    SectorRead,
    SignalRead,
)
from src.apps.patterns.api.deps import PatternQueryDep
from src.apps.patterns.api.errors import pattern_coin_not_found_error
from src.apps.patterns.api.presenters import (
    coin_regime_read,
    discovered_pattern_read,
    pattern_feature_read,
    pattern_read,
    sector_metrics_response,
    sector_read,
    signal_read,
)

router = APIRouter(tags=["patterns:read"])


@router.get("/patterns", response_model=list[PatternRead], summary="List patterns")
async def read_patterns(service: PatternQueryDep) -> list[PatternRead]:
    return [pattern_read(item) for item in await service.list_patterns()]


@router.get("/patterns/features", response_model=list[PatternFeatureRead], summary="List pattern features")
async def read_pattern_features(service: PatternQueryDep) -> list[PatternFeatureRead]:
    return [pattern_feature_read(item) for item in await service.list_pattern_features()]


@router.get(
    "/patterns/discovered",
    response_model=list[DiscoveredPatternRead],
    summary="List discovered patterns",
)
async def read_discovered_patterns(
    service: PatternQueryDep,
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[DiscoveredPatternRead]:
    items = await service.list_discovered_patterns(timeframe=timeframe, limit=limit)
    return [discovered_pattern_read(item) for item in items]


@router.get(
    "/coins/{symbol}/patterns",
    response_model=list[SignalRead],
    summary="List coin pattern signals",
)
async def read_coin_patterns(
    symbol: str,
    service: PatternQueryDep,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[SignalRead]:
    items = await service.list_coin_patterns(symbol, limit=limit)
    return [signal_read(item) for item in items]


@router.get("/coins/{symbol}/regime", response_model=CoinRegimeRead, summary="Read coin regime")
async def read_coin_regime(symbol: str, service: PatternQueryDep) -> CoinRegimeRead:
    payload = await service.get_coin_regime_read_by_symbol(symbol)
    if payload is None:
        raise pattern_coin_not_found_error(symbol)
    return coin_regime_read(payload)


@router.get("/sectors", response_model=list[SectorRead], summary="List sectors")
async def read_sectors(service: PatternQueryDep) -> list[SectorRead]:
    return [sector_read(item) for item in await service.list_sectors()]


@router.get("/sectors/metrics", response_model=SectorMetricsResponse, summary="Read sector metrics")
async def read_sector_metrics(
    service: PatternQueryDep,
    timeframe: int | None = Query(default=None),
) -> SectorMetricsResponse:
    return sector_metrics_response(await service.list_sector_metrics(timeframe=timeframe))
