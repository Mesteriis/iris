from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from src.apps.signals.query_services import SignalQueryService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow


def get_signal_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> SignalQueryService:
    return SignalQueryService(uow.session)


SignalQueryDep = Annotated[SignalQueryService, Depends(get_signal_query_service)]


__all__ = ["SignalQueryDep"]
