from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.predictions.schemas import PredictionRead
from app.apps.predictions.services import list_predictions_async
from app.core.db.session import get_db

router = APIRouter(tags=["predictions"])


@router.get("/predictions", response_model=list[PredictionRead])
async def read_predictions(
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[PredictionRead]:
    return list(await list_predictions_async(db, limit=limit, status=status))
