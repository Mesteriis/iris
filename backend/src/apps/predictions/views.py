from fastapi import APIRouter, Depends, Query

from src.apps.predictions.query_services import PredictionQueryService
from src.apps.predictions.schemas import PredictionRead
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow

router = APIRouter(tags=["predictions"])
DB_UOW = Depends(get_uow)


@router.get("/predictions", response_model=list[PredictionRead])
async def read_predictions(
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = Query(default=None),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[PredictionRead]:
    items = await PredictionQueryService(uow.session).list_predictions(limit=limit, status=status)
    return [PredictionRead.model_validate(item) for item in items]
