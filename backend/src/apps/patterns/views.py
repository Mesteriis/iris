from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

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
from src.apps.patterns.services import (
    get_coin_regimes_async,
    list_coin_patterns_async,
    list_discovered_patterns_async,
    list_pattern_features_async,
    list_patterns_async,
    list_sector_metrics_async,
    list_sectors_async,
    update_pattern_async,
    update_pattern_feature_async,
)
from src.apps.signals.schemas import SignalRead
from src.core.db.session import get_db

router = APIRouter(tags=["patterns"])


@router.get("/patterns", response_model=list[PatternRead])
async def read_patterns(db: AsyncSession = Depends(get_db)) -> list[PatternRead]:
    return list(await list_patterns_async(db))


@router.get("/patterns/features", response_model=list[PatternFeatureRead])
async def read_pattern_features(db: AsyncSession = Depends(get_db)) -> list[PatternFeatureRead]:
    return list(await list_pattern_features_async(db))


@router.patch("/patterns/features/{feature_slug}", response_model=PatternFeatureRead)
async def patch_pattern_feature(
    feature_slug: str,
    payload: PatternFeatureUpdate,
    db: AsyncSession = Depends(get_db),
) -> PatternFeatureRead:
    row = await update_pattern_feature_async(db, feature_slug, enabled=payload.enabled)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pattern feature '{feature_slug}' was not found.",
        )
    return PatternFeatureRead.model_validate(row)


@router.patch("/patterns/{slug}", response_model=PatternRead)
async def patch_pattern(
    slug: str,
    payload: PatternUpdate,
    db: AsyncSession = Depends(get_db),
) -> PatternRead:
    try:
        row = await update_pattern_async(
            db,
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
    return PatternRead.model_validate(row)


@router.get("/patterns/discovered", response_model=list[DiscoveredPatternRead])
async def read_discovered_patterns(
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[DiscoveredPatternRead]:
    return list(await list_discovered_patterns_async(db, timeframe=timeframe, limit=limit))


@router.get("/coins/{symbol}/patterns", response_model=list[SignalRead])
async def read_coin_patterns(
    symbol: str,
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[SignalRead]:
    return list(await list_coin_patterns_async(db, symbol, limit=limit))


@router.get("/coins/{symbol}/regime", response_model=CoinRegimeRead)
async def read_coin_regime(symbol: str, db: AsyncSession = Depends(get_db)) -> CoinRegimeRead:
    payload = await get_coin_regimes_async(db, symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinRegimeRead.model_validate(payload)


@router.get("/sectors", response_model=list[SectorRead], tags=["sectors"])
async def read_sectors(db: AsyncSession = Depends(get_db)) -> list[SectorRead]:
    return list(await list_sectors_async(db))


@router.get("/sectors/metrics", response_model=SectorMetricsResponse, tags=["sectors"])
async def read_sector_metrics(
    timeframe: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> SectorMetricsResponse:
    return SectorMetricsResponse.model_validate(await list_sector_metrics_async(db, timeframe=timeframe))
