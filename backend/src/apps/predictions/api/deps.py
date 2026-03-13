from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from src.apps.predictions.query_services import PredictionQueryService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow


def get_prediction_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> PredictionQueryService:
    return PredictionQueryService(uow.session)


PredictionQueryDep = Annotated[PredictionQueryService, Depends(get_prediction_query_service)]

__all__ = ["PredictionQueryDep"]
