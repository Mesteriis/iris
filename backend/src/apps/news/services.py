from __future__ import annotations

import re
from typing import Any

from src.apps.market_data.domain import utc_now
from src.apps.news.constants import (
    DEFAULT_NEWS_POLL_LIMIT,
    NEWS_EVENT_ITEM_INGESTED,
)
from src.apps.news.exceptions import InvalidNewsSourceConfigurationError, TelegramOnboardingError
from src.apps.news.models import NewsItem, NewsSource
from src.apps.news.plugins import create_news_plugin, get_news_plugin
from src.apps.news.query_services import NewsQueryService
from src.apps.news.repositories import NewsItemRepository, NewsSourceRepository
from src.apps.news.schemas import (
    NewsSourceCreate,
    NewsSourceRead,
    NewsSourceUpdate,
    TelegramDialogRead,
    TelegramDialogSelection,
    TelegramDialogSubscribeResult,
    TelegramDialogsRequest,
    TelegramBulkSubscribeRead,
    TelegramBulkSubscribeRequest,
    TelegramSessionCodeRequest,
    TelegramSessionCodeRequestRead,
    TelegramSessionConfirmRead,
    TelegramSessionConfirmRequest,
    TelegramSourceFromDialogCreate,
    TelegramWizardFieldRead,
    TelegramWizardRead,
    TelegramWizardStepRead,
)
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
    return sorted(set(match.group(1) for match in _SYMBOL_HINT_PATTERN.finditer(text)))


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
    ) -> dict[str, object]:
        source = await self._sources.get_for_update(source_id)
        if source is None:
            return {"status": "error", "reason": "source_not_found", "source_id": source_id}
        if not source.enabled:
            return {"status": "skipped", "reason": "source_disabled", "source_id": source_id}

        plugin = create_news_plugin(source)
        try:
            result = await plugin.fetch_items(cursor=dict(source.cursor_json or {}), limit=limit)
        except Exception as exc:
            source.last_error = str(exc)[:255]
            source.last_polled_at = utc_now()
            return {
                "status": "error",
                "reason": "poll_failed",
                "source_id": source_id,
                "plugin_name": source.plugin_name,
                "error": source.last_error,
            }

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

        return {
            "status": "ok",
            "source_id": int(source.id),
            "plugin_name": source.plugin_name,
            "fetched": len(result.items),
            "created": len(created_items),
            "cursor": dict(source.cursor_json or {}),
        }

    async def poll_enabled_sources(self, *, limit_per_source: int = DEFAULT_NEWS_POLL_LIMIT) -> dict[str, object]:
        rows = await self._sources.list_enabled_for_update()
        items = []
        for source in rows:
            items.append(await self.poll_source(source_id=int(source.id), limit=limit_per_source))
        return {
            "status": "ok",
            "sources": len(rows),
            "items": items,
            "created": sum(int(item.get("created", 0)) for item in items),
        }


class TelegramSessionOnboardingService:
    async def request_code(self, payload: TelegramSessionCodeRequest) -> TelegramSessionCodeRequestRead:
        TelegramClient, StringSession, _SessionPasswordNeededError, _tg_types = self._load_telethon()
        del _SessionPasswordNeededError
        del _tg_types
        try:
            async with TelegramClient(StringSession(), int(payload.api_id), payload.api_hash) as client:
                result = await client.send_code_request(payload.phone_number)
        except Exception as exc:  # pragma: no cover
            raise TelegramOnboardingError(str(exc)) from exc
        return TelegramSessionCodeRequestRead(
            status="code_sent",
            phone_number=payload.phone_number,
            phone_code_hash=str(result.phone_code_hash),
        )

    async def confirm_code(self, payload: TelegramSessionConfirmRequest) -> TelegramSessionConfirmRead:
        TelegramClient, StringSession, SessionPasswordNeededError, _tg_types = self._load_telethon()
        del _tg_types
        try:
            async with TelegramClient(StringSession(), int(payload.api_id), payload.api_hash) as client:
                try:
                    me = await client.sign_in(
                        phone=payload.phone_number,
                        code=payload.code,
                        phone_code_hash=payload.phone_code_hash,
                    )
                except SessionPasswordNeededError:
                    if not payload.password:
                        return TelegramSessionConfirmRead(status="password_required")
                    me = await client.sign_in(password=payload.password)
                me = me or await client.get_me()
                session_string = client.session.save()
        except Exception as exc:  # pragma: no cover
            raise TelegramOnboardingError(str(exc)) from exc

        display_name = " ".join(
            part for part in (getattr(me, "first_name", None), getattr(me, "last_name", None)) if part
        ).strip()
        return TelegramSessionConfirmRead(
            status="authorized",
            session_string=str(session_string),
            user_id=int(getattr(me, "id", 0)) if getattr(me, "id", None) is not None else None,
            username=str(getattr(me, "username", "")) or None,
            display_name=display_name or None,
        )

    async def list_dialogs(self, payload: TelegramDialogsRequest) -> list[TelegramDialogRead]:
        TelegramClient, StringSession, _SessionPasswordNeededError, tg_types = self._load_telethon()
        del _SessionPasswordNeededError
        try:
            async with TelegramClient(StringSession(payload.session_string), int(payload.api_id), payload.api_hash) as client:
                rows = [
                    self._serialize_dialog(dialog, tg_types)
                    async for dialog in client.iter_dialogs(limit=int(payload.limit))
                ]
        except Exception as exc:  # pragma: no cover
            raise TelegramOnboardingError(str(exc)) from exc
        return [
            row
            for row in rows
            if payload.include_users or row.entity_type != "user"
        ]

    @staticmethod
    def _load_telethon():
        try:
            from telethon import TelegramClient
            from telethon.errors import SessionPasswordNeededError
            from telethon import types as tg_types
            from telethon.sessions import StringSession
        except ImportError as exc:  # pragma: no cover
            raise TelegramOnboardingError(
                "telegram_user onboarding requires the optional 'telethon' dependency to be installed."
            ) from exc
        return TelegramClient, StringSession, SessionPasswordNeededError, tg_types

    @staticmethod
    def _serialize_dialog(dialog, tg_types) -> TelegramDialogRead:
        entity = dialog.entity
        username = str(getattr(entity, "username", "")) or None
        title = str(getattr(dialog, "title", "") or getattr(entity, "title", "") or username or getattr(entity, "first_name", "") or getattr(entity, "id"))
        if isinstance(entity, tg_types.Channel):
            entity_type = "channel"
            access_hash = str(getattr(entity, "access_hash", "")) or None
            settings_hint: dict[str, Any] = {
                "entity_type": "channel",
                "entity_id": int(entity.id),
            }
            if access_hash is not None:
                settings_hint["entity_access_hash"] = access_hash
            if username is not None:
                settings_hint["channel"] = f"@{username}"
        elif isinstance(entity, tg_types.Chat):
            entity_type = "chat"
            access_hash = None
            settings_hint = {
                "entity_type": "chat",
                "entity_id": int(entity.id),
                "channel": title,
            }
        else:
            entity_type = "user"
            access_hash = str(getattr(entity, "access_hash", "")) or None
            settings_hint = {
                "channel": f"@{username}" if username else title,
            }
        return TelegramDialogRead(
            entity_id=int(getattr(entity, "id", 0)),
            entity_type=entity_type,
            title=title,
            username=username,
            access_hash=access_hash,
            selectable=entity_type in {"channel", "chat"},
            settings_hint=settings_hint,
        )


class TelegramSourceProvisioningService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._news = NewsService(uow)

    async def create_source_from_dialog(self, payload: TelegramSourceFromDialogCreate) -> NewsSourceRead:
        request = self._build_source_request(
            api_id=payload.api_id,
            api_hash=payload.api_hash,
            session_string=payload.session_string,
            dialog=payload.dialog,
        )
        return await self._news.create_source(request)

    async def bulk_subscribe(self, payload: TelegramBulkSubscribeRequest) -> TelegramBulkSubscribeRead:
        created: list[NewsSourceRead] = []
        results: list[TelegramDialogSubscribeResult] = []
        for dialog in payload.dialogs:
            try:
                source = await self.create_source_from_dialog(
                    TelegramSourceFromDialogCreate(
                        api_id=payload.api_id,
                        api_hash=payload.api_hash,
                        session_string=payload.session_string,
                        dialog=dialog,
                    )
                )
            except InvalidNewsSourceConfigurationError as exc:
                results.append(
                    TelegramDialogSubscribeResult(
                        title=dialog.title,
                        display_name=dialog.display_name or dialog.title,
                        status="skipped",
                        reason=str(exc),
                    )
                )
                continue
            created.append(source)
            results.append(
                TelegramDialogSubscribeResult(
                    title=dialog.title,
                    display_name=source.display_name,
                    status="created",
                    source_id=source.id,
                )
            )
        return TelegramBulkSubscribeRead(
            created_count=len(created),
            skipped_count=sum(1 for item in results if item.status != "created"),
            created=created,
            results=results,
        )

    @staticmethod
    def wizard_spec() -> TelegramWizardRead:
        return TelegramWizardRead(
            plugin_name="telegram_user",
            title="Telegram News Source Wizard",
            supported_dialog_types=["channel", "chat"],
            private_dialog_support=True,
            steps=[
                TelegramWizardStepRead(
                    id="request_code",
                    title="Request Login Code",
                    description="Send Telegram login code to the user's phone number.",
                    endpoint="/news/onboarding/telegram/session/request",
                    method="POST",
                    fields=[
                        TelegramWizardFieldRead(id="api_id", label="API ID", type="number", required=True),
                        TelegramWizardFieldRead(id="api_hash", label="API Hash", type="text", required=True, secret=True),
                        TelegramWizardFieldRead(id="phone_number", label="Phone Number", type="tel", required=True),
                    ],
                ),
                TelegramWizardStepRead(
                    id="confirm_code",
                    title="Confirm Session",
                    description="Exchange the received code for a reusable MTProto session string.",
                    endpoint="/news/onboarding/telegram/session/confirm",
                    method="POST",
                    fields=[
                        TelegramWizardFieldRead(id="code", label="Login Code", type="text", required=True),
                        TelegramWizardFieldRead(id="password", label="2FA Password", type="password", required=False, secret=True),
                    ],
                ),
                TelegramWizardStepRead(
                    id="list_dialogs",
                    title="Choose Dialogs",
                    description="Load channels and groups available to the authenticated Telegram account.",
                    endpoint="/news/onboarding/telegram/dialogs",
                    method="POST",
                    fields=[
                        TelegramWizardFieldRead(id="session_string", label="Session String", type="text", required=True, secret=True),
                        TelegramWizardFieldRead(id="include_users", label="Include User Chats", type="boolean", required=False),
                    ],
                ),
                TelegramWizardStepRead(
                    id="create_sources",
                    title="Create News Sources",
                    description="Create one or more IRIS news sources from the selected Telegram dialogs.",
                    endpoint="/news/onboarding/telegram/sources/bulk",
                    method="POST",
                    fields=[
                        TelegramWizardFieldRead(id="dialogs", label="Selected Dialogs", type="array", required=True),
                    ],
                ),
            ],
            notes=[
                "Public channels can be stored via @username.",
                "Private channels require entity_id plus entity_access_hash.",
                "Private legacy groups can be stored via entity_type=chat and entity_id.",
                "Only explicitly selected dialogs are polled; IRIS does not ingest all dialogs automatically.",
            ],
            source_payload_example={
                "plugin_name": "telegram_user",
                "display_name": "Alpha Channel",
                "credentials": {
                    "api_id": 1001,
                    "api_hash": "telegram-api-hash",
                    "session_string": "telegram-session-string",
                },
                "settings": {
                    "entity_type": "channel",
                    "entity_id": 101,
                    "entity_access_hash": "999",
                    "channel": "@alpha",
                },
            },
        )

    @staticmethod
    def _build_source_request(
        *,
        api_id: int,
        api_hash: str,
        session_string: str,
        dialog: TelegramDialogSelection,
    ) -> NewsSourceCreate:
        entity_type = dialog.entity_type.strip().lower()
        if entity_type not in {"channel", "chat"}:
            raise InvalidNewsSourceConfigurationError(
                f"Telegram dialog '{dialog.title}' is not selectable for news polling."
            )
        display_name = (dialog.display_name or dialog.title).strip()
        settings: dict[str, Any] = {
            "entity_type": entity_type,
            "entity_id": int(dialog.entity_id),
        }
        if dialog.max_items_per_poll is not None:
            settings["max_results"] = int(dialog.max_items_per_poll)
        if dialog.username:
            settings["channel"] = f"@{dialog.username.lstrip('@')}"
        if entity_type == "channel":
            if dialog.access_hash in (None, ""):
                raise InvalidNewsSourceConfigurationError(
                    f"Telegram dialog '{dialog.title}' is missing access_hash for channel subscription."
                )
            settings["entity_access_hash"] = str(dialog.access_hash)
        return NewsSourceCreate(
            plugin_name="telegram_user",
            display_name=display_name,
            enabled=bool(dialog.enabled),
            credentials={
                "api_id": int(api_id),
                "api_hash": api_hash,
                "session_string": session_string,
            },
            settings=settings,
        )


__all__ = ["NewsService", "TelegramSessionOnboardingService", "TelegramSourceProvisioningService"]
