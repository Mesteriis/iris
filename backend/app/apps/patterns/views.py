from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.apps.patterns.schemas import (
    CoinRegimeRead,
    DiscoveredPatternRead,
    PatternFeatureRead,
    PatternFeatureUpdate,
    PatternRead,
    PatternUpdate,
    SectorMetricsResponse,
    SectorRead,
)
from app.apps.patterns.services import (
    get_coin_regimes,
    list_coin_patterns,
    list_discovered_patterns,
    list_pattern_features,
    list_patterns,
    list_sector_metrics,
    list_sectors,
    update_pattern,
    update_pattern_feature,
)
from app.apps.signals.schemas import SignalRead
from app.core.db.session import get_db

router = APIRouter(tags=["patterns"])


@router.get("/patterns", response_model=list[PatternRead])
def read_patterns(db: Session = Depends(get_db)) -> list[PatternRead]:
    return list(list_patterns(db))


@router.get("/patterns/features", response_model=list[PatternFeatureRead])
def read_pattern_features(db: Session = Depends(get_db)) -> list[PatternFeatureRead]:
    return list(list_pattern_features(db))


@router.patch("/patterns/features/{feature_slug}", response_model=PatternFeatureRead)
def patch_pattern_feature(
    feature_slug: str,
    payload: PatternFeatureUpdate,
    db: Session = Depends(get_db),
) -> PatternFeatureRead:
    row = update_pattern_feature(db, feature_slug, enabled=payload.enabled)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pattern feature '{feature_slug}' was not found.",
        )
    return PatternFeatureRead.model_validate(row)


@router.patch("/patterns/{slug}", response_model=PatternRead)
def patch_pattern(
    slug: str,
    payload: PatternUpdate,
    db: Session = Depends(get_db),
) -> PatternRead:
    try:
        row = update_pattern(
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
def read_discovered_patterns(
    timeframe: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[DiscoveredPatternRead]:
    return list(list_discovered_patterns(db, timeframe=timeframe, limit=limit))


@router.get("/coins/{symbol}/patterns", response_model=list[SignalRead])
def read_coin_patterns(
    symbol: str,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[SignalRead]:
    return list(list_coin_patterns(db, symbol, limit=limit))


@router.get("/coins/{symbol}/regime", response_model=CoinRegimeRead)
def read_coin_regime(symbol: str, db: Session = Depends(get_db)) -> CoinRegimeRead:
    payload = get_coin_regimes(db, symbol)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Coin '{symbol.upper()}' was not found.",
        )
    return CoinRegimeRead.model_validate(payload)


@router.get("/sectors", response_model=list[SectorRead], tags=["sectors"])
def read_sectors(db: Session = Depends(get_db)) -> list[SectorRead]:
    return list(list_sectors(db))


@router.get("/sectors/metrics", response_model=SectorMetricsResponse, tags=["sectors"])
def read_sector_metrics(
    timeframe: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SectorMetricsResponse:
    return SectorMetricsResponse.model_validate(list_sector_metrics(db, timeframe=timeframe))
