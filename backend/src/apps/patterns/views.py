from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.apps.patterns.query_services import PatternQueryService
from src.apps.patterns.schemas import (
    CoinRegimeRead,
    DiscoveredPatternRead,
    PatternFeatureRead,
    PatternFeatureUpdate,
    PatternRead,
    PatternUpdate,
    SectorMetricsResponse,
    SectorRead,
)
from src.apps.patterns.services import PatternAdminService
from src.apps.signals.schemas import SignalRead
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow

router = APIRouter(tags=["patterns"])
DB_UOW = Depends(get_uow)


@router.get("/patterns", response_model=list[PatternRead])
async def read_patterns(uow: BaseAsyncUnitOfWork = DB_UOW) -> list[PatternRead]:
    items = await PatternQueryService(uow.session).list_patterns()
    return [PatternRead.model_validate(item) for item in items]


@router.get("/patterns/features", response_model=list[PatternFeatureRead])
async def read_pattern_features(uow: BaseAsyncUnitOfWork = DB_UOW) -> list[PatternFeatureRead]:
    items = await PatternQueryService(uow.session).list_pattern_features()
    return [PatternFeatureRead.model_validate(item) for item in items]


@router.patch("/patterns/features/{feature_slug}", response_model=PatternFeatureRead)
async def patch_pattern_feature(
    feature_slug: str,
    payload: PatternFeatureUpdate,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> PatternFeatureRead:
    row = await PatternAdminService(uow).update_pattern_feature(feature_slug, enabled=payload.enabled)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pattern feature '{feature_slug}' was not found.",
        )
    await uow.commit()
    return PatternFeatureRead.model_validate(row)


@router.patch("/patterns/{slug}", response_model=PatternRead)
async def patch_pattern(
    slug: str,
    payload: PatternUpdate,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> PatternRead:
    try:
        row = await PatternAdminService(uow).update_pattern(
            slug,
            enabled=payload.enabled,
            lifecycle_state=payload.lifecycle_state,
            cpu_cost=payload.cpu_cost,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pattern '{slug}' was not found.",
        )
    await uow.commit()
    return PatternRead.model_validate(row)


@router.get("/patterns/discovered", response_model=list[DiscoveredPatternRead])
async def read_discovered_patterns(
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[DiscoveredPatternRead]:
    items = await PatternQueryService(uow.session).list_discovered_patterns(timeframe=timeframe, limit=limit)
    return [DiscoveredPatternRead.model_validate(item) for item in items]


@router.get("/coins/{symbol}/patterns", response_model=list[SignalRead])
async def read_coin_patterns(
    symbol: str,
    limit: int = Query(default=200, ge=1, le=1000),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[SignalRead]:
    items = await PatternQueryService(uow.session).list_coin_patterns(symbol, limit=limit)
    return [SignalRead.model_validate(item) for item in items]


@router.get("/coins/{symbol}/regime", response_model=CoinRegimeRead)
async def read_coin_regime(symbol: str, uow: BaseAsyncUnitOfWork = DB_UOW) -> CoinRegimeRead:
    payload = await PatternQueryService(uow.session).get_coin_regime_read_by_symbol(symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinRegimeRead.model_validate(payload)


@router.get("/sectors", response_model=list[SectorRead], tags=["sectors"])
async def read_sectors(uow: BaseAsyncUnitOfWork = DB_UOW) -> list[SectorRead]:
    items = await PatternQueryService(uow.session).list_sectors()
    return [SectorRead.model_validate(item) for item in items]


@router.get("/sectors/metrics", response_model=SectorMetricsResponse, tags=["sectors"])
async def read_sector_metrics(
    timeframe: int | None = Query(default=None),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> SectorMetricsResponse:
    return SectorMetricsResponse.model_validate(
        await PatternQueryService(uow.session).list_sector_metrics(timeframe=timeframe)
    )
