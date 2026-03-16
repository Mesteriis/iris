from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from iris.apps.notifications.models import AINotification
from iris.core.db.persistence import freeze_json_value


@runtime_checkable
class _SupportsInt(Protocol):
    def __int__(self) -> int: ...


def _required_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool | int | str | bytes | bytearray):
        return int(value)
    if isinstance(value, _SupportsInt):
        return int(value)
    raise TypeError(f"{field_name} must be int-compatible, got {type(value).__name__}")


@dataclass(slots=True, frozen=True)
class NotificationReadModel:
    id: int
    coin_id: int
    symbol: str | None
    sector: str | None
    timeframe: int
    severity: str
    urgency: str
    content_kind: str
    content_json: Any
    refs_json: Any
    context_json: Any
    provider: str
    model: str
    prompt_name: str
    prompt_version: int
    source_event_type: str
    source_event_id: str
    source_stream_id: str | None
    causation_id: str | None
    correlation_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class NotificationCoinContextReadModel:
    coin_id: int
    symbol: str
    sector_code: str | None


def notification_read_model_from_orm(notification: AINotification) -> NotificationReadModel:
    return NotificationReadModel(
        id=_required_int(notification.id, field_name="id"),
        coin_id=_required_int(notification.coin_id, field_name="coin_id"),
        symbol=str(notification.symbol) if notification.symbol is not None else None,
        sector=str(notification.sector) if notification.sector is not None else None,
        timeframe=_required_int(notification.timeframe, field_name="timeframe"),
        severity=str(notification.severity),
        urgency=str(notification.urgency),
        content_kind=str(notification.content_kind),
        content_json=freeze_json_value(dict(notification.content_json or {})),
        refs_json=freeze_json_value(dict(notification.refs_json or {})),
        context_json=freeze_json_value(dict(notification.context_json or {})),
        provider=str(notification.provider),
        model=str(notification.model),
        prompt_name=str(notification.prompt_name),
        prompt_version=_required_int(notification.prompt_version, field_name="prompt_version"),
        source_event_type=str(notification.source_event_type),
        source_event_id=str(notification.source_event_id),
        source_stream_id=str(notification.source_stream_id) if notification.source_stream_id is not None else None,
        causation_id=str(notification.causation_id) if notification.causation_id is not None else None,
        correlation_id=str(notification.correlation_id) if notification.correlation_id is not None else None,
        created_at=notification.created_at,
        updated_at=notification.updated_at,
    )


__all__ = [
    "NotificationCoinContextReadModel",
    "NotificationReadModel",
    "notification_read_model_from_orm",
]
