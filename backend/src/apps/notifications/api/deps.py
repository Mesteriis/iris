from typing import Annotated

from fastapi import Depends

from src.apps.notifications.query_services import NotificationQueryService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow

_UOW_DEP = Depends(get_uow)


def get_notification_query_service(uow: BaseAsyncUnitOfWork = _UOW_DEP) -> NotificationQueryService:
    return NotificationQueryService(uow.session)


NotificationQueryDep = Annotated[NotificationQueryService, Depends(get_notification_query_service)]

__all__ = ["NotificationQueryDep"]
