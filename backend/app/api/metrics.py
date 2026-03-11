from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.coin_metrics import CoinMetricsRead
from app.services.analytics_service import list_coin_metrics

router = APIRouter(prefix="/coins", tags=["metrics"])


@router.get("/metrics", response_model=list[CoinMetricsRead])
def read_coin_metrics(db: Session = Depends(get_db)) -> list[CoinMetricsRead]:
    return list(list_coin_metrics(db))
