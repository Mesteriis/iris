from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.market_data.models import Coin
from src.apps.news.models import NewsItem, NewsItemLink, NewsSource
from src.apps.news.read_models import CoinAliasReadModel
from src.core.db.persistence import AsyncRepository


class NewsSourceRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="news", repository_name="NewsSourceRepository")

    async def get_by_id(self, source_id: int) -> NewsSource | None:
        self._log_debug("repo.get_news_source", mode="read", source_id=source_id)
        source = await self.session.get(NewsSource, source_id)
        self._log_debug("repo.get_news_source.result", mode="read", found=source is not None)
        return source

    async def get_for_update(self, source_id: int) -> NewsSource | None:
        self._log_debug("repo.get_news_source_for_update", mode="write", source_id=source_id, lock=True)
        source = await self.session.scalar(
            select(NewsSource).where(NewsSource.id == source_id).with_for_update().limit(1)
        )
        self._log_debug("repo.get_news_source_for_update.result", mode="write", found=source is not None)
        return source

    async def get_by_plugin_display_name(
        self,
        *,
        plugin_name: str,
        display_name: str,
        exclude_source_id: int | None = None,
    ) -> NewsSource | None:
        self._log_debug(
            "repo.get_news_source_by_plugin_display_name",
            mode="write",
            plugin_name=plugin_name,
            display_name=display_name,
            exclude_source_id=exclude_source_id,
        )
        stmt = select(NewsSource).where(
            NewsSource.plugin_name == plugin_name,
            NewsSource.display_name == display_name,
        )
        if exclude_source_id is not None:
            stmt = stmt.where(NewsSource.id != exclude_source_id)
        source = await self.session.scalar(stmt.limit(1))
        self._log_debug("repo.get_news_source_by_plugin_display_name.result", mode="write", found=source is not None)
        return source

    async def list_enabled_for_update(self) -> list[NewsSource]:
        self._log_debug("repo.list_enabled_news_sources_for_update", mode="write")
        rows = (
            await self.session.execute(
                select(NewsSource)
                .where(NewsSource.enabled.is_(True))
                .order_by(NewsSource.updated_at.asc(), NewsSource.id.asc())
            )
        ).scalars().all()
        items = list(rows)
        self._log_debug("repo.list_enabled_news_sources_for_update.result", mode="write", count=len(items))
        return items

    async def add(self, source: NewsSource) -> NewsSource:
        self._log_info("repo.add_news_source", mode="write", plugin_name=source.plugin_name)
        self.session.add(source)
        await self.session.flush()
        return source

    async def delete(self, source: NewsSource) -> None:
        self._log_info("repo.delete_news_source", mode="write", source_id=int(source.id))
        await self.session.delete(source)
        await self.session.flush()

    async def refresh(self, source: NewsSource) -> None:
        await self.session.refresh(source)


class NewsItemRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="news", repository_name="NewsItemRepository")

    async def get_for_update(self, item_id: int) -> NewsItem | None:
        self._log_debug("repo.get_news_item_for_update", mode="write", item_id=item_id, lock=True)
        item = await self.session.scalar(select(NewsItem).where(NewsItem.id == item_id).with_for_update().limit(1))
        self._log_debug("repo.get_news_item_for_update.result", mode="write", found=item is not None)
        return item

    async def list_existing_external_ids(self, *, source_id: int, external_ids: list[str]) -> set[str]:
        self._log_debug(
            "repo.list_existing_news_external_ids",
            mode="write",
            source_id=source_id,
            external_id_count=len(external_ids),
        )
        if not external_ids:
            return set()
        rows = (
            await self.session.execute(
                select(NewsItem.external_id)
                .where(NewsItem.source_id == source_id, NewsItem.external_id.in_(external_ids))
            )
        ).scalars().all()
        items = {str(value) for value in rows}
        self._log_debug("repo.list_existing_news_external_ids.result", mode="write", count=len(items))
        return items

    async def add_many(self, items: list[NewsItem]) -> list[NewsItem]:
        self._log_info("repo.add_news_items", mode="write", bulk=True, count=len(items))
        if not items:
            return items
        self.session.add_all(items)
        await self.session.flush()
        return items


class NewsItemLinkRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="news", repository_name="NewsItemLinkRepository")

    async def delete_by_item_id(self, item_id: int) -> None:
        self._log_info("repo.delete_news_item_links", mode="write", news_item_id=item_id, bulk=True)
        await self.session.execute(delete(NewsItemLink).where(NewsItemLink.news_item_id == item_id))
        await self.session.flush()

    async def add_many(self, links: list[NewsItemLink]) -> list[NewsItemLink]:
        self._log_info("repo.add_news_item_links", mode="write", bulk=True, count=len(links))
        if not links:
            return links
        self.session.add_all(links)
        await self.session.flush()
        return links


class NewsMarketDataRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="news", repository_name="NewsMarketDataRepository")

    async def list_coin_aliases(self) -> tuple[CoinAliasReadModel, ...]:
        self._log_debug("repo.list_coin_aliases", mode="read")
        rows = (
            await self.session.execute(
                select(Coin.id, Coin.symbol, Coin.name, Coin.sort_order)
                .where(Coin.deleted_at.is_(None), Coin.enabled.is_(True))
                .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
            )
        ).all()
        items = tuple(
            CoinAliasReadModel(
                coin_id=int(row.id),
                coin_symbol=str(row.symbol),
                coin_name=str(row.name),
                sort_order=int(getattr(row, "sort_order", 0) or 0),
            )
            for row in rows
        )
        self._log_debug("repo.list_coin_aliases.result", mode="read", count=len(items))
        return items


__all__ = [
    "NewsItemLinkRepository",
    "NewsItemRepository",
    "NewsMarketDataRepository",
    "NewsSourceRepository",
]
