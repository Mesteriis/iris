from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from app.apps.market_data.domain import ensure_utc
from app.apps.news.constants import (
    DEFAULT_DISCORD_API_BASE_URL,
    DEFAULT_NEWS_POLL_LIMIT,
    DEFAULT_X_API_BASE_URL,
    MAX_NEWS_POLL_LIMIT,
    NEWS_SOURCE_PLUGIN_DISCORD_BOT,
    NEWS_SOURCE_PLUGIN_TELEGRAM_USER,
    NEWS_SOURCE_PLUGIN_TRUTH_SOCIAL,
    NEWS_SOURCE_PLUGIN_X,
)
from app.apps.news.exceptions import InvalidNewsSourceConfigurationError, UnsupportedNewsPluginError

if TYPE_CHECKING:
    from app.apps.news.models import NewsSource


@dataclass(frozen=True, slots=True)
class NewsPluginDescriptor:
    name: str
    display_name: str
    description: str
    auth_mode: str
    supported: bool
    supports_user_identity: bool = False
    required_credentials: tuple[str, ...] = ()
    required_settings: tuple[str, ...] = ()
    runtime_dependencies: tuple[str, ...] = ()
    unsupported_reason: str | None = None


@dataclass(frozen=True, slots=True)
class FetchedNewsItem:
    external_id: str
    published_at: datetime
    author_handle: str | None
    channel_name: str | None
    title: str | None
    content_text: str
    url: str | None
    payload_json: dict[str, Any]


@dataclass(frozen=True, slots=True)
class NewsFetchResult:
    items: list[FetchedNewsItem]
    next_cursor: dict[str, Any]


class NewsSourcePlugin(ABC):
    descriptor: NewsPluginDescriptor

    def __init__(self, source: "NewsSource") -> None:
        self.source = source
        self.credentials = dict(source.credentials_json or {})
        self.settings = dict(source.settings_json or {})

    @classmethod
    def validate_configuration(
        cls,
        *,
        credentials: dict[str, Any],
        settings: dict[str, Any],
    ) -> None:
        if not cls.descriptor.supported:
            raise UnsupportedNewsPluginError(cls.descriptor.unsupported_reason or f"Plugin '{cls.descriptor.name}' is unsupported.")
        missing_credentials = [
            field
            for field in cls.descriptor.required_credentials
            if credentials.get(field) in (None, "")
        ]
        missing_settings = [
            field
            for field in cls.descriptor.required_settings
            if settings.get(field) in (None, "")
        ]
        if missing_credentials or missing_settings:
            missing = ", ".join([*(f"credentials.{item}" for item in missing_credentials), *(f"settings.{item}" for item in missing_settings)])
            raise InvalidNewsSourceConfigurationError(f"Missing required configuration fields: {missing}.")

    @abstractmethod
    async def fetch_items(self, *, cursor: dict[str, Any], limit: int = DEFAULT_NEWS_POLL_LIMIT) -> NewsFetchResult:
        raise NotImplementedError


_REGISTRY: dict[str, type[NewsSourcePlugin]] = {}


def register_news_plugin(name: str, plugin_cls: type[NewsSourcePlugin]) -> None:
    _REGISTRY[name.strip().lower()] = plugin_cls


def get_news_plugin(name: str) -> type[NewsSourcePlugin] | None:
    return _REGISTRY.get(name.strip().lower())


def list_registered_news_plugins() -> dict[str, type[NewsSourcePlugin]]:
    return dict(sorted(_REGISTRY.items()))


def create_news_plugin(source: "NewsSource") -> NewsSourcePlugin:
    plugin_cls = get_news_plugin(source.plugin_name)
    if plugin_cls is None:
        raise ValueError(f"Unsupported news plugin '{source.plugin_name}'.")
    return plugin_cls(source)


class XNewsPlugin(NewsSourcePlugin):
    descriptor = NewsPluginDescriptor(
        name=NEWS_SOURCE_PLUGIN_X,
        display_name="X / Twitter",
        description="Poll posts from a specific X user timeline through the official X API.",
        auth_mode="bearer_or_user_token",
        supported=True,
        supports_user_identity=False,
        required_settings=("user_id",),
    )

    @classmethod
    def validate_configuration(
        cls,
        *,
        credentials: dict[str, Any],
        settings: dict[str, Any],
    ) -> None:
        super().validate_configuration(credentials=credentials, settings=settings)
        if credentials.get("bearer_token") in (None, "") and credentials.get("access_token") in (None, ""):
            raise InvalidNewsSourceConfigurationError(
                "X source requires credentials.bearer_token or credentials.access_token."
            )

    async def fetch_items(self, *, cursor: dict[str, Any], limit: int = DEFAULT_NEWS_POLL_LIMIT) -> NewsFetchResult:
        token = str(self.credentials.get("bearer_token") or self.credentials.get("access_token") or "").strip()
        if not token:
            raise InvalidNewsSourceConfigurationError("X source token is not configured.")
        user_id = str(self.settings["user_id"]).strip()
        max_results = min(max(int(self.settings.get("max_results", limit)), 5), MAX_NEWS_POLL_LIMIT)
        params: dict[str, Any] = {
            "max_results": max_results,
            "tweet.fields": "created_at,public_metrics,author_id,text",
        }
        if cursor.get("since_id") is not None:
            params["since_id"] = str(cursor["since_id"])

        base_url = str(self.settings.get("api_base_url") or DEFAULT_X_API_BASE_URL).rstrip("/")
        url = f"{base_url}/users/{user_id}/tweets"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
        payload = response.json()
        rows = payload.get("data", [])
        items = [
            FetchedNewsItem(
                external_id=str(row["id"]),
                published_at=ensure_utc(datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))),
                author_handle=str(row.get("author_id")) if row.get("author_id") is not None else None,
                channel_name=self.source.display_name,
                title=None,
                content_text=str(row.get("text") or ""),
                url=f"https://x.com/i/web/status/{row['id']}",
                payload_json=row,
            )
            for row in rows
        ]
        next_cursor = dict(cursor)
        if items:
            next_cursor["since_id"] = max((item.external_id for item in items), key=lambda value: int(value))
        return NewsFetchResult(items=items, next_cursor=next_cursor)


class DiscordBotNewsPlugin(NewsSourcePlugin):
    descriptor = NewsPluginDescriptor(
        name=NEWS_SOURCE_PLUGIN_DISCORD_BOT,
        display_name="Discord Bot",
        description="Poll a Discord channel using an official bot token.",
        auth_mode="bot_token",
        supported=True,
        supports_user_identity=False,
        required_credentials=("bot_token",),
        required_settings=("channel_id",),
    )

    async def fetch_items(self, *, cursor: dict[str, Any], limit: int = DEFAULT_NEWS_POLL_LIMIT) -> NewsFetchResult:
        channel_id = str(self.settings["channel_id"]).strip()
        token = str(self.credentials["bot_token"]).strip()
        params: dict[str, Any] = {"limit": min(max(limit, 1), MAX_NEWS_POLL_LIMIT)}
        if cursor.get("after") is not None:
            params["after"] = str(cursor["after"])
        base_url = str(self.settings.get("api_base_url") or DEFAULT_DISCORD_API_BASE_URL).rstrip("/")
        url = f"{base_url}/channels/{channel_id}/messages"
        headers = {"Authorization": f"Bot {token}"}

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
        rows = response.json()
        items = [
            FetchedNewsItem(
                external_id=str(row["id"]),
                published_at=ensure_utc(datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00"))),
                author_handle=str((row.get("author") or {}).get("username")) if row.get("author") is not None else None,
                channel_name=self.source.display_name,
                title=None,
                content_text=str(row.get("content") or ""),
                url=(row.get("attachments") or [{}])[0].get("url") if row.get("attachments") else None,
                payload_json=row,
            )
            for row in reversed(rows)
        ]
        next_cursor = dict(cursor)
        if items:
            next_cursor["after"] = max((item.external_id for item in items), key=lambda value: int(value))
        return NewsFetchResult(items=items, next_cursor=next_cursor)


class TelegramUserNewsPlugin(NewsSourcePlugin):
    descriptor = NewsPluginDescriptor(
        name=NEWS_SOURCE_PLUGIN_TELEGRAM_USER,
        display_name="Telegram User",
        description="Poll a Telegram channel or chat through a user-authenticated MTProto session.",
        auth_mode="user_session",
        supported=True,
        supports_user_identity=True,
        required_credentials=("api_id", "api_hash", "session_string"),
        runtime_dependencies=("telethon",),
    )

    @staticmethod
    def _load_telethon():
        try:
            from telethon import TelegramClient, types
            from telethon.sessions import StringSession
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "telegram_user polling requires the optional 'telethon' dependency to be installed."
            ) from exc
        return TelegramClient, StringSession, types

    @classmethod
    def validate_configuration(
        cls,
        *,
        credentials: dict[str, Any],
        settings: dict[str, Any],
    ) -> None:
        super().validate_configuration(credentials=credentials, settings={})
        if settings.get("channel") not in (None, ""):
            return
        entity_id = settings.get("entity_id")
        entity_type = str(settings.get("entity_type") or "").strip().lower()
        if entity_id in (None, "") or not entity_type:
            raise InvalidNewsSourceConfigurationError(
                "Telegram source requires settings.channel or settings.entity_id with settings.entity_type."
            )
        if entity_type not in {"channel", "chat"}:
            raise InvalidNewsSourceConfigurationError(
                "Telegram settings.entity_type must be 'channel' or 'chat'."
            )
        if entity_type == "channel" and settings.get("entity_access_hash") in (None, ""):
            raise InvalidNewsSourceConfigurationError(
                "Telegram channel sources require settings.entity_access_hash for private channel access."
            )

    async def fetch_items(self, *, cursor: dict[str, Any], limit: int = DEFAULT_NEWS_POLL_LIMIT) -> NewsFetchResult:
        TelegramClient, StringSession, types = self._load_telethon()

        api_id = int(self.credentials["api_id"])
        api_hash = str(self.credentials["api_hash"])
        session_string = str(self.credentials["session_string"])
        after_id = int(cursor.get("after_id") or 0)

        # NOTE:
        # Telegram user access relies on MTProto and has no standard-library async
        # client. The optional Telethon dependency is imported lazily and executed
        # only inside the dedicated polling task, outside the HTTP request path.
        async with TelegramClient(StringSession(session_string), api_id, api_hash) as client:
            entity = await self._resolve_entity(client, types)
            rows = [
                message
                async for message in client.iter_messages(
                    entity,
                    limit=min(max(limit, 1), MAX_NEWS_POLL_LIMIT),
                    min_id=after_id,
                    reverse=True,
                )
            ]

        username = getattr(entity, "username", None)
        items = [
            FetchedNewsItem(
                external_id=str(row.id),
                published_at=ensure_utc(row.date),
                author_handle=str(getattr(row, "sender_id", "")) or None,
                channel_name=f"@{username}" if username else self.source.display_name,
                title=None,
                content_text=str(getattr(row, "message", "") or ""),
                url=f"https://t.me/{username}/{row.id}" if username else None,
                payload_json={"id": row.id, "message": getattr(row, "message", ""), "sender_id": getattr(row, "sender_id", None)},
            )
            for row in rows
        ]
        next_cursor = dict(cursor)
        if items:
            next_cursor["after_id"] = max(int(item.external_id) for item in items)
        return NewsFetchResult(items=items, next_cursor=next_cursor)

    async def _resolve_entity(self, client, types):
        channel = self.settings.get("channel")
        if channel not in (None, ""):
            return await client.get_entity(str(channel))
        entity_type = str(self.settings.get("entity_type") or "").strip().lower()
        entity_id = int(self.settings["entity_id"])
        if entity_type == "chat":
            return types.InputPeerChat(entity_id)
        access_hash = int(self.settings["entity_access_hash"])
        return types.InputPeerChannel(entity_id, access_hash)


class TruthSocialUnsupportedPlugin(NewsSourcePlugin):
    descriptor = NewsPluginDescriptor(
        name=NEWS_SOURCE_PLUGIN_TRUTH_SOCIAL,
        display_name="Truth Social",
        description="Reserved placeholder. Disabled because no public official developer API is available.",
        auth_mode="unsupported",
        supported=False,
        supports_user_identity=False,
        unsupported_reason="Truth Social has no public official developer API in the current IRIS integration policy.",
    )

    async def fetch_items(self, *, cursor: dict[str, Any], limit: int = DEFAULT_NEWS_POLL_LIMIT) -> NewsFetchResult:
        del cursor, limit
        raise UnsupportedNewsPluginError(self.descriptor.unsupported_reason or "Unsupported plugin.")


register_news_plugin(NEWS_SOURCE_PLUGIN_X, XNewsPlugin)
register_news_plugin(NEWS_SOURCE_PLUGIN_TELEGRAM_USER, TelegramUserNewsPlugin)
register_news_plugin(NEWS_SOURCE_PLUGIN_DISCORD_BOT, DiscordBotNewsPlugin)
register_news_plugin(NEWS_SOURCE_PLUGIN_TRUTH_SOCIAL, TruthSocialUnsupportedPlugin)


__all__ = [
    "DiscordBotNewsPlugin",
    "FetchedNewsItem",
    "NewsFetchResult",
    "NewsPluginDescriptor",
    "NewsSourcePlugin",
    "TelegramUserNewsPlugin",
    "TruthSocialUnsupportedPlugin",
    "XNewsPlugin",
    "create_news_plugin",
    "get_news_plugin",
    "list_registered_news_plugins",
    "register_news_plugin",
]
