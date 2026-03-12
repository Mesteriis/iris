from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.core.db.persistence import freeze_json_value


def _source_status(*, enabled: bool, last_error: str | None) -> str:
    if not enabled:
        return "disabled"
    if last_error:
        return "error"
    return "active"


def _credential_fields_present(credentials: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(key for key, value in credentials.items() if value not in (None, "", [], {}, ())))


@dataclass(slots=True, frozen=True)
class NewsPluginReadModel:
    name: str
    display_name: str
    description: str
    auth_mode: str
    supported: bool
    supports_user_identity: bool
    required_credentials: tuple[str, ...]
    required_settings: tuple[str, ...]
    runtime_dependencies: tuple[str, ...]
    unsupported_reason: str | None


@dataclass(slots=True, frozen=True)
class NewsSourceReadModel:
    id: int
    plugin_name: str
    display_name: str
    enabled: bool
    status: str
    auth_mode: str
    credential_fields_present: tuple[str, ...]
    settings: Any
    cursor: Any
    last_polled_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class NewsItemLinkReadModel:
    coin_id: int
    coin_symbol: str
    matched_symbol: str
    link_type: str
    confidence: float


@dataclass(slots=True, frozen=True)
class NewsItemReadModel:
    id: int
    source_id: int
    plugin_name: str
    external_id: str
    published_at: datetime
    author_handle: str | None
    channel_name: str | None
    title: str | None
    content_text: str
    url: str | None
    symbol_hints: tuple[str, ...]
    payload_json: Any
    normalization_status: str
    normalized_payload_json: Any
    normalized_at: datetime | None
    sentiment_score: float | None
    relevance_score: float | None
    links: tuple[NewsItemLinkReadModel, ...]


@dataclass(slots=True, frozen=True)
class CoinAliasReadModel:
    coin_id: int
    coin_symbol: str
    coin_name: str
    sort_order: int


def news_plugin_read_model_from_descriptor(descriptor) -> NewsPluginReadModel:
    return NewsPluginReadModel(
        name=str(descriptor.name),
        display_name=str(descriptor.display_name),
        description=str(descriptor.description),
        auth_mode=str(descriptor.auth_mode),
        supported=bool(descriptor.supported),
        supports_user_identity=bool(descriptor.supports_user_identity),
        required_credentials=tuple(str(value) for value in descriptor.required_credentials),
        required_settings=tuple(str(value) for value in descriptor.required_settings),
        runtime_dependencies=tuple(str(value) for value in descriptor.runtime_dependencies),
        unsupported_reason=str(descriptor.unsupported_reason) if descriptor.unsupported_reason is not None else None,
    )


def news_source_read_model_from_orm(source) -> NewsSourceReadModel:
    credentials = dict(source.credentials_json or {})
    return NewsSourceReadModel(
        id=int(source.id),
        plugin_name=str(source.plugin_name),
        display_name=str(source.display_name),
        enabled=bool(source.enabled),
        status=_source_status(enabled=bool(source.enabled), last_error=str(source.last_error) if source.last_error else None),
        auth_mode=str(source.auth_mode),
        credential_fields_present=_credential_fields_present(credentials),
        settings=freeze_json_value(dict(source.settings_json or {})),
        cursor=freeze_json_value(dict(source.cursor_json or {})),
        last_polled_at=source.last_polled_at,
        last_error=str(source.last_error) if source.last_error is not None else None,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def news_item_link_read_model_from_orm(link) -> NewsItemLinkReadModel:
    return NewsItemLinkReadModel(
        coin_id=int(link.coin_id),
        coin_symbol=str(link.coin_symbol),
        matched_symbol=str(link.matched_symbol),
        link_type=str(link.link_type),
        confidence=float(link.confidence),
    )


def news_item_read_model_from_orm(item) -> NewsItemReadModel:
    ordered_links = tuple(
        news_item_link_read_model_from_orm(link)
        for link in sorted(item.links, key=lambda current: (-float(current.confidence), int(current.coin_id)))
    )
    return NewsItemReadModel(
        id=int(item.id),
        source_id=int(item.source_id),
        plugin_name=str(item.plugin_name),
        external_id=str(item.external_id),
        published_at=item.published_at,
        author_handle=str(item.author_handle) if item.author_handle is not None else None,
        channel_name=str(item.channel_name) if item.channel_name is not None else None,
        title=str(item.title) if item.title is not None else None,
        content_text=str(item.content_text),
        url=str(item.url) if item.url is not None else None,
        symbol_hints=tuple(str(value) for value in item.symbol_hints or ()),
        payload_json=freeze_json_value(dict(item.payload_json or {})),
        normalization_status=str(item.normalization_status),
        normalized_payload_json=freeze_json_value(dict(item.normalized_payload_json or {})),
        normalized_at=item.normalized_at,
        sentiment_score=float(item.sentiment_score) if item.sentiment_score is not None else None,
        relevance_score=float(item.relevance_score) if item.relevance_score is not None else None,
        links=ordered_links,
    )

