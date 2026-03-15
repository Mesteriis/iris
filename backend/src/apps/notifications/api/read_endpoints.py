from __future__ import annotations

from fastapi import APIRouter, Query

from src.apps.notifications.api.contracts import NotificationRead
from src.apps.notifications.api.deps import NotificationQueryDep
from src.apps.notifications.api.errors import notification_not_found_error
from src.apps.notifications.api.presenters import notification_read
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["notifications:read"])


@router.get("/notifications", response_model=list[NotificationRead], summary="List persisted humanized notifications")
async def read_notifications(
    service: NotificationQueryDep,
    request_locale: RequestLocaleDep,
    limit: int = Query(default=50, ge=1, le=500),
    coin_id: int | None = Query(default=None, ge=1),
    source_event_type: str | None = Query(default=None),
) -> list[NotificationRead]:
    items = await service.list_notifications(
        limit=limit,
        coin_id=coin_id,
        source_event_type=source_event_type,
    )
    return [notification_read(item, locale=request_locale) for item in items]


@router.get("/notifications/{notification_id}", response_model=NotificationRead, summary="Read a persisted notification")
async def read_notification(
    notification_id: int,
    service: NotificationQueryDep,
    request_locale: RequestLocaleDep,
) -> NotificationRead:
    item = await service.get_notification_read_by_id(notification_id)
    if item is None:
        raise notification_not_found_error(locale=request_locale)
    return notification_read(item, locale=request_locale)


__all__ = ["router"]
