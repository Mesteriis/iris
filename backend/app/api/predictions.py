from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.prediction import PredictionRead
from app.services.predictions_service import list_predictions

router = APIRouter(tags=["predictions"])


@router.get("/predictions", response_model=list[PredictionRead])
def read_predictions(
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[PredictionRead]:
    return list(list_predictions(db, limit=limit, status=status))
