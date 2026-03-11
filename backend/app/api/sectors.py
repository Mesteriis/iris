from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.sector import SectorMetricsResponse, SectorRead
from app.services.patterns_service import list_sector_metrics, list_sectors

router = APIRouter(tags=["sectors"])


@router.get("/sectors", response_model=list[SectorRead])
def read_sectors(db: Session = Depends(get_db)) -> list[SectorRead]:
    return list(list_sectors(db))


@router.get("/sectors/metrics", response_model=SectorMetricsResponse)
def read_sector_metrics(
    timeframe: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SectorMetricsResponse:
    return SectorMetricsResponse.model_validate(list_sector_metrics(db, timeframe=timeframe))
