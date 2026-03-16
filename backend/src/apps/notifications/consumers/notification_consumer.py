from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.notifications.constants import SUPPORTED_NOTIFICATION_SOURCE_EVENTS
from src.apps.notifications.services import NotificationService, NotificationSideEffectDispatcher
from src.core.db.session import AsyncSessionLocal
from src.core.db.uow import AsyncUnitOfWork
from src.runtime.streams.types import IrisEvent


class NotificationConsumer:
    def __init__(self, *, session_factory: Callable[[], AsyncSession] = AsyncSessionLocal) -> None:
        self._session_factory = session_factory

    async def handle_event(self, event: IrisEvent) -> None:
        if event.event_type not in SUPPORTED_NOTIFICATION_SOURCE_EVENTS or event.coin_id <= 0:
            return
        async with AsyncUnitOfWork(session_factory=self._session_factory) as uow:
            result = await NotificationService(uow).create_from_event(event)
            await uow.commit()
        await NotificationSideEffectDispatcher().apply_creation(result)


__all__ = ["NotificationConsumer"]
