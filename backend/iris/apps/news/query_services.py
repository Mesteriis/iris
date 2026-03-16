from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from iris.apps.news.models import NewsItem, NewsSource
from iris.apps.news.plugins import list_registered_news_plugins
from iris.apps.news.read_models import (
    NewsItemReadModel,
    NewsPluginReadModel,
    NewsSourceReadModel,
    news_item_read_model_from_orm,
    news_plugin_read_model_from_descriptor,
    news_source_read_model_from_orm,
)
from iris.core.db.persistence import AsyncQueryService


class NewsQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="news", service_name="NewsQueryService")

    async def list_plugins(self) -> tuple[NewsPluginReadModel, ...]:
        self._log_debug("query.list_news_plugins", mode="read")
        items = tuple(
            news_plugin_read_model_from_descriptor(plugin_cls.descriptor)
            for _, plugin_cls in sorted(list_registered_news_plugins().items(), key=lambda item: item[0])
        )
        self._log_debug("query.list_news_plugins.result", mode="read", count=len(items))
        return items

    async def list_sources(self) -> tuple[NewsSourceReadModel, ...]:
        self._log_debug("query.list_news_sources", mode="read")
        rows = (
            await self.session.execute(
                select(NewsSource).order_by(NewsSource.plugin_name.asc(), NewsSource.display_name.asc())
            )
        ).scalars().all()
        items = tuple(news_source_read_model_from_orm(item) for item in rows)
        self._log_debug("query.list_news_sources.result", mode="read", count=len(items))
        return items

    async def get_source_read_by_id(self, source_id: int) -> NewsSourceReadModel | None:
        self._log_debug("query.get_news_source_read_by_id", mode="read", source_id=source_id)
        source = await self.session.get(NewsSource, source_id)
        if source is None:
            self._log_debug("query.get_news_source_read_by_id.result", mode="read", found=False)
            return None
        item = news_source_read_model_from_orm(source)
        self._log_debug("query.get_news_source_read_by_id.result", mode="read", found=True)
        return item

    async def list_items(
        self,
        *,
        source_id: int | None = None,
        limit: int,
    ) -> tuple[NewsItemReadModel, ...]:
        self._log_debug("query.list_news_items", mode="read", source_id=source_id, limit=limit, loading_profile="full")
        stmt = (
            select(NewsItem)
            .options(selectinload(NewsItem.links))
            .order_by(NewsItem.published_at.desc())
            .limit(limit)
        )
        if source_id is not None:
            stmt = stmt.where(NewsItem.source_id == source_id)
        rows = (await self.session.execute(stmt)).scalars().all()
        items = tuple(news_item_read_model_from_orm(item) for item in rows)
        self._log_debug("query.list_news_items.result", mode="read", count=len(items))
        return items


__all__ = ["NewsQueryService"]
