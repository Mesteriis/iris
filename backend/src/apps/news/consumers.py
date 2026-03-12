from __future__ import annotations

from src.apps.news.pipeline import NewsCorrelationService, NewsNormalizationService
from src.core.db.session import AsyncSessionLocal
from src.runtime.streams.types import IrisEvent


class NewsNormalizationConsumer:
    def __init__(self, *, session_factory=AsyncSessionLocal) -> None:
        self._session_factory = session_factory

    async def handle_event(self, event: IrisEvent) -> None:
        if event.event_type != "news_item_ingested":
            return
        item_id = int(event.payload.get("item_id") or 0)
        if item_id <= 0:
            return
        async with self._session_factory() as db:
            await NewsNormalizationService(db).normalize_item(item_id=item_id)


class NewsCorrelationConsumer:
    def __init__(self, *, session_factory=AsyncSessionLocal) -> None:
        self._session_factory = session_factory

    async def handle_event(self, event: IrisEvent) -> None:
        if event.event_type != "news_item_normalized":
            return
        item_id = int(event.payload.get("item_id") or 0)
        if item_id <= 0:
            return
        async with self._session_factory() as db:
            await NewsCorrelationService(db).correlate_item(item_id=item_id)


__all__ = ["NewsCorrelationConsumer", "NewsNormalizationConsumer"]
