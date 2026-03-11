from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.apps.predictions.schemas import PredictionRead
from app.apps.predictions.services import list_predictions
from app.core.db.session import get_db

router = APIRouter(tags=["predictions"])


@router.get("/predictions", response_model=list[PredictionRead])
def read_predictions(
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[PredictionRead]:
    return list(list_predictions(db, limit=limit, status=status))
