import re
from typing import Any

from src.apps.market_data.domain import utc_now
from src.apps.news.constants import DEFAULT_NEWS_POLL_LIMIT, NEWS_EVENT_ITEM_INGESTED
from src.apps.news.contracts import NewsSourceCreate, NewsSourceRead, NewsSourceUpdate
from src.apps.news.exceptions import InvalidNewsSourceConfigurationError
from src.apps.news.models import NewsItem, NewsSource
from src.apps.news.plugins import create_news_plugin, get_news_plugin
from src.apps.news.query_services import NewsQueryService
from src.apps.news.repositories import NewsItemRepository, NewsSourceRepository
from src.apps.news.results import NewsEnabledPollResult, NewsSourcePollResult
from src.core.db.uow import BaseAsyncUnitOfWork
from src.runtime.streams.publisher import publish_event

_SYMBOL_HINT_PATTERN = re.compile(r"(?<![A-Z0-9])\$([A-Z][A-Z0-9]{1,9})(?![A-Z0-9])")


def _merge_mapping(base: dict[str, Any], patch: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if patch is None:
        return merged
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def _extract_symbol_hints(text: str) -> list[str]:
    return sorted({match.group(1) for match in _SYMBOL_HINT_PATTERN.finditer(text)})


class NewsService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._queries = NewsQueryService(uow.session)
        self._sources = NewsSourceRepository(uow.session)
        self._items = NewsItemRepository(uow.session)

    def _publish_after_commit(self, event_type: str, payload: dict[str, object]) -> None:
        self._uow.add_after_commit_action(
            lambda event_type=event_type, payload=dict(payload): publish_event(event_type, payload)
        )

    async def create_source(self, payload: NewsSourceCreate) -> NewsSourceRead:
        plugin_name = payload.plugin_name.strip().lower()
        plugin_cls = get_news_plugin(plugin_name)
        if plugin_cls is None:
            raise InvalidNewsSourceConfigurationError(f"Unsupported news plugin '{payload.plugin_name}'.")
        plugin_cls.validate_configuration(credentials=payload.credentials, settings=payload.settings)
        existing = await self._sources.get_by_plugin_display_name(
            plugin_name=plugin_name,
            display_name=payload.display_name.strip(),
        )
        if existing is not None:
            raise InvalidNewsSourceConfigurationError(
                f"News source '{payload.display_name.strip()}' already exists for plugin '{plugin_name}'."
            )

        source = await self._sources.add(
            NewsSource(
                plugin_name=plugin_name,
                display_name=payload.display_name.strip(),
                enabled=payload.enabled,
                auth_mode=plugin_cls.descriptor.auth_mode,
                credentials_json=dict(payload.credentials),
                settings_json=dict(payload.settings),
                cursor_json={},
            )
        )
        item = await self._queries.get_source_read_by_id(int(source.id))
        return NewsSourceRead.model_validate(item if item is not None else source)

    async def update_source(self, source_id: int, payload: NewsSourceUpdate) -> NewsSourceRead | None:
        source = await self._sources.get_for_update(source_id)
        if source is None:
            return None

        plugin_cls = get_news_plugin(source.plugin_name)
        if plugin_cls is None:
            raise InvalidNewsSourceConfigurationError(f"Unsupported news plugin '{source.plugin_name}'.")

        display_name = payload.display_name.strip() if payload.display_name is not None else source.display_name
        merged_credentials = _merge_mapping(dict(source.credentials_json or {}), payload.credentials)
        merged_settings = _merge_mapping(dict(source.settings_json or {}), payload.settings)
        plugin_cls.validate_configuration(credentials=merged_credentials, settings=merged_settings)

        if display_name != source.display_name:
            existing = await self._sources.get_by_plugin_display_name(
                plugin_name=source.plugin_name,
                display_name=display_name,
                exclude_source_id=int(source.id),
            )
            if existing is not None:
                raise InvalidNewsSourceConfigurationError(
                    f"News source '{display_name}' already exists for plugin '{source.plugin_name}'."
                )
            source.display_name = display_name

        if payload.enabled is not None:
            source.enabled = payload.enabled
        if payload.credentials is not None:
            source.credentials_json = merged_credentials
        if payload.settings is not None:
            source.settings_json = merged_settings
        if payload.reset_cursor:
            source.cursor_json = {}
        if payload.clear_error:
            source.last_error = None

        await self._uow.flush()
        await self._sources.refresh(source)
        item = await self._queries.get_source_read_by_id(int(source.id))
        return NewsSourceRead.model_validate(item if item is not None else source)

    async def delete_source(self, source_id: int) -> bool:
        source = await self._sources.get_for_update(source_id)
        if source is None:
            return False
        await self._sources.delete(source)
        return True

    async def poll_source(
        self,
        *,
        source_id: int,
        limit: int = DEFAULT_NEWS_POLL_LIMIT,
    ) -> NewsSourcePollResult:
        source = await self._sources.get_for_update(source_id)
        if source is None:
            return NewsSourcePollResult(status="error", reason="source_not_found", source_id=source_id)
        if not source.enabled:
            return NewsSourcePollResult(status="skipped", reason="source_disabled", source_id=source_id)

        plugin = create_news_plugin(source)
        try:
            result = await plugin.fetch_items(cursor=dict(source.cursor_json or {}), limit=limit)
        except Exception as exc:
            source.last_error = str(exc)[:255]
            source.last_polled_at = utc_now()
            return NewsSourcePollResult(
                status="error",
                reason="poll_failed",
                source_id=source_id,
                plugin_name=source.plugin_name,
                error=source.last_error,
            )

        external_ids = [item.external_id for item in result.items]
        existing_ids = await self._items.list_existing_external_ids(source_id=source_id, external_ids=external_ids)

        created_items: list[NewsItem] = []
        for item in result.items:
            if item.external_id in existing_ids:
                continue
            created_items.append(
                NewsItem(
                    source_id=int(source.id),
                    plugin_name=source.plugin_name,
                    external_id=item.external_id,
                    published_at=item.published_at,
                    author_handle=item.author_handle,
                    channel_name=item.channel_name,
                    title=item.title,
                    content_text=item.content_text,
                    url=item.url,
                    symbol_hints=_extract_symbol_hints(item.content_text),
                    payload_json=item.payload_json,
                    normalization_status="pending",
                    normalized_payload_json={},
                )
            )

        await self._items.add_many(created_items)
        source.cursor_json = dict(result.next_cursor)
        source.last_polled_at = utc_now()
        source.last_error = None
        for item in created_items:
            self._publish_after_commit(
                NEWS_EVENT_ITEM_INGESTED,
                {
                    "coin_id": 0,
                    "timeframe": 0,
                    "timestamp": item.published_at,
                    "item_id": int(item.id),
                    "source_id": int(item.source_id),
                    "plugin_name": item.plugin_name,
                    "external_id": item.external_id,
                    "author_handle": item.author_handle,
                    "channel_name": item.channel_name,
                    "url": item.url,
                    "symbol_hints": item.symbol_hints,
                },
            )

        return NewsSourcePollResult(
            status="ok",
            source_id=int(source.id),
            plugin_name=source.plugin_name,
            fetched=len(result.items),
            created=len(created_items),
            cursor=dict(source.cursor_json or {}),
        )

    async def poll_enabled_sources(
        self,
        *,
        limit_per_source: int = DEFAULT_NEWS_POLL_LIMIT,
    ) -> NewsEnabledPollResult:
        rows = await self._sources.list_enabled_for_update()
        items = tuple(
            [
                await self.poll_source(source_id=int(source.id), limit=limit_per_source)
                for source in rows
            ]
        )
        return NewsEnabledPollResult(
            status="ok",
            sources=len(rows),
            items=items,
            created=sum(item.created for item in items),
        )


__all__ = ["NewsService"]
