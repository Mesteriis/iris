from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from iris.apps.news.pipeline import NewsCorrelationService, NewsNormalizationService
from iris.core.db.session import AsyncSessionLocal
from iris.core.db.uow import AsyncUnitOfWork
from iris.runtime.streams.types import IrisEvent


class NewsNormalizationConsumer:
    def __init__(self, *, session_factory: Callable[[], AsyncSession] = AsyncSessionLocal) -> None:
        self._session_factory = session_factory

    async def handle_event(self, event: IrisEvent) -> None:
        if event.event_type != "news_item_ingested":
            return
        item_id = int(event.payload.get("item_id") or 0)
        if item_id <= 0:
            return
        async with AsyncUnitOfWork(session_factory=self._session_factory) as uow:
            await NewsNormalizationService(uow).normalize_item(item_id=item_id)
            await uow.commit()


class NewsCorrelationConsumer:
    def __init__(self, *, session_factory: Callable[[], AsyncSession] = AsyncSessionLocal) -> None:
        self._session_factory = session_factory

    async def handle_event(self, event: IrisEvent) -> None:
        if event.event_type != "news_item_normalized":
            return
        item_id = int(event.payload.get("item_id") or 0)
        if item_id <= 0:
            return
        async with AsyncUnitOfWork(session_factory=self._session_factory) as uow:
            await NewsCorrelationService(uow).correlate_item(item_id=item_id)
            await uow.commit()


__all__ = ["NewsCorrelationConsumer", "NewsNormalizationConsumer"]
