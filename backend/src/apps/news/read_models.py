from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from src.core.db.persistence import freeze_json_value


@runtime_checkable
class _SupportsInt(Protocol):
    def __int__(self) -> int: ...


@runtime_checkable
class _SupportsFloat(Protocol):
    def __float__(self) -> float: ...


class _NewsPluginDescriptorLike(Protocol):
    @property
    def name(self) -> object: ...

    @property
    def display_name(self) -> object: ...

    @property
    def description(self) -> object: ...

    @property
    def auth_mode(self) -> object: ...

    @property
    def supported(self) -> object: ...

    @property
    def supports_user_identity(self) -> object: ...

    @property
    def required_credentials(self) -> Iterable[object]: ...

    @property
    def required_settings(self) -> Iterable[object]: ...

    @property
    def runtime_dependencies(self) -> Iterable[object]: ...

    @property
    def unsupported_reason(self) -> object | None: ...


class _NewsSourceLike(Protocol):
    @property
    def id(self) -> object: ...

    @property
    def plugin_name(self) -> object: ...

    @property
    def display_name(self) -> object: ...

    @property
    def enabled(self) -> object: ...

    @property
    def auth_mode(self) -> object: ...

    @property
    def credentials_json(self) -> Mapping[str, Any] | None: ...

    @property
    def settings_json(self) -> Mapping[str, Any] | None: ...

    @property
    def cursor_json(self) -> Mapping[str, Any] | None: ...

    @property
    def last_polled_at(self) -> datetime | None: ...

    @property
    def last_error(self) -> object | None: ...

    @property
    def created_at(self) -> datetime: ...

    @property
    def updated_at(self) -> datetime: ...


class _NewsItemLinkLike(Protocol):
    @property
    def coin_id(self) -> object: ...

    @property
    def coin_symbol(self) -> object: ...

    @property
    def matched_symbol(self) -> object: ...

    @property
    def link_type(self) -> object: ...

    @property
    def confidence(self) -> object: ...


class _NewsItemLike(Protocol):
    @property
    def id(self) -> object: ...

    @property
    def source_id(self) -> object: ...

    @property
    def plugin_name(self) -> object: ...

    @property
    def external_id(self) -> object: ...

    @property
    def published_at(self) -> datetime: ...

    @property
    def author_handle(self) -> object | None: ...

    @property
    def channel_name(self) -> object | None: ...

    @property
    def title(self) -> object | None: ...

    @property
    def content_text(self) -> object: ...

    @property
    def url(self) -> object | None: ...

    @property
    def symbol_hints(self) -> Iterable[object] | None: ...

    @property
    def payload_json(self) -> Mapping[str, Any] | None: ...

    @property
    def normalization_status(self) -> object: ...

    @property
    def normalized_payload_json(self) -> Mapping[str, Any] | None: ...

    @property
    def normalized_at(self) -> datetime | None: ...

    @property
    def sentiment_score(self) -> object | None: ...

    @property
    def relevance_score(self) -> object | None: ...

    @property
    def links(self) -> Iterable[_NewsItemLinkLike]: ...


def _required_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool | int | str | bytes | bytearray):
        return int(value)
    if isinstance(value, _SupportsInt):
        return int(value)
    raise TypeError(f"{field_name} must be int-compatible, got {type(value).__name__}")


def _required_float(value: object, *, field_name: str) -> float:
    if isinstance(value, bool | int | float | str | bytes | bytearray):
        return float(value)
    if isinstance(value, _SupportsFloat):
        return float(value)
    if isinstance(value, _SupportsInt):
        return float(int(value))
    raise TypeError(f"{field_name} must be float-compatible, got {type(value).__name__}")


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


def news_plugin_read_model_from_descriptor(descriptor: _NewsPluginDescriptorLike) -> NewsPluginReadModel:
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


def news_source_read_model_from_orm(source: _NewsSourceLike) -> NewsSourceReadModel:
    credentials = dict(source.credentials_json or {})
    return NewsSourceReadModel(
        id=_required_int(source.id, field_name="id"),
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


def news_item_link_read_model_from_orm(link: _NewsItemLinkLike) -> NewsItemLinkReadModel:
    return NewsItemLinkReadModel(
        coin_id=_required_int(link.coin_id, field_name="coin_id"),
        coin_symbol=str(link.coin_symbol),
        matched_symbol=str(link.matched_symbol),
        link_type=str(link.link_type),
        confidence=_required_float(link.confidence, field_name="confidence"),
    )


def news_item_read_model_from_orm(item: _NewsItemLike) -> NewsItemReadModel:
    ordered_links = tuple(
        news_item_link_read_model_from_orm(link)
        for link in sorted(
            item.links,
            key=lambda current: (
                -_required_float(current.confidence, field_name="confidence"),
                _required_int(current.coin_id, field_name="coin_id"),
            ),
        )
    )
    return NewsItemReadModel(
        id=_required_int(item.id, field_name="id"),
        source_id=_required_int(item.source_id, field_name="source_id"),
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
        sentiment_score=_required_float(item.sentiment_score, field_name="sentiment_score")
        if item.sentiment_score is not None
        else None,
        relevance_score=_required_float(item.relevance_score, field_name="relevance_score")
        if item.relevance_score is not None
        else None,
        links=ordered_links,
    )
