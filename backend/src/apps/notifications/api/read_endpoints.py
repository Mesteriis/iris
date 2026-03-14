from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from src.apps.notifications.api.contracts import NotificationRead
from src.apps.notifications.api.deps import NotificationQueryDep
from src.apps.notifications.api.presenters import notification_read

router = APIRouter(tags=["notifications:read"])


@router.get("/notifications", response_model=list[NotificationRead], summary="List persisted humanized notifications")
async def read_notifications(
    service: NotificationQueryDep,
    limit: int = Query(default=50, ge=1, le=500),
    coin_id: int | None = Query(default=None, ge=1),
    source_event_type: str | None = Query(default=None),
    language: str | None = Query(default=None),
) -> list[NotificationRead]:
    items = await service.list_notifications(
        limit=limit,
        coin_id=coin_id,
        source_event_type=source_event_type,
        language=language,
    )
    return [notification_read(item) for item in items]


@router.get("/notifications/{notification_id}", response_model=NotificationRead, summary="Read a persisted notification")
async def read_notification(
    notification_id: int,
    service: NotificationQueryDep,
) -> NotificationRead:
    item = await service.get_notification_read_by_id(notification_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    return notification_read(item)


__all__ = ["router"]
