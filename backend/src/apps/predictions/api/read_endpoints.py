from fastapi import APIRouter, Query

from src.apps.predictions.api.contracts import PredictionRead
from src.apps.predictions.api.deps import PredictionQueryDep
from src.apps.predictions.api.presenters import prediction_read

router = APIRouter(tags=["predictions:read"])


@router.get("/predictions", response_model=list[PredictionRead], summary="List predictions")
async def read_predictions(
    service: PredictionQueryDep,
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = Query(default=None),
) -> list[PredictionRead]:
    return [prediction_read(item) for item in await service.list_predictions(limit=limit, status=status)]
