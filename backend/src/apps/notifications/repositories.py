from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.notifications.models import AINotification
from src.core.db.persistence import AsyncRepository


class NotificationRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="notifications", repository_name="NotificationRepository")

    async def get_by_source_event(
        self,
        *,
        source_event_type: str,
        source_event_id: str,
        language: str,
    ) -> AINotification | None:
        self._log_debug(
            "repo.get_notification_by_source_event",
            mode="write",
            source_event_type=source_event_type,
            source_event_id=source_event_id,
            language=language,
        )
        row = await self.session.scalar(
            select(AINotification)
            .where(
                AINotification.source_event_type == source_event_type,
                AINotification.source_event_id == source_event_id,
                AINotification.language == language,
            )
            .limit(1)
        )
        self._log_debug("repo.get_notification_by_source_event.result", mode="write", found=row is not None)
        return row

    async def add_notification(self, notification: AINotification) -> AINotification:
        self._log_info(
            "repo.add_notification",
            mode="write",
            source_event_type=notification.source_event_type,
            source_event_id=notification.source_event_id,
            language=notification.language,
        )
        self.session.add(notification)
        await self.session.flush()
        await self.session.refresh(notification)
        return notification


__all__ = ["NotificationRepository"]
