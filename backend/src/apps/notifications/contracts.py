from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.core.ai.telemetry import AIExecutionMetadata
from src.core.i18n import MessageDescriptor


class NotificationHumanizationOutput(BaseModel):
    title: str
    message: str
    severity: Literal["info", "warning", "critical"]
    urgency: Literal["low", "medium", "high"]

    model_config = ConfigDict(extra="forbid")


class NotificationCreationStatus(StrEnum):
    CREATED = "created"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class NotificationPendingEvent:
    event_type: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NotificationHumanizationResult:
    title: str
    message: str
    severity: Literal["info", "warning", "critical"]
    urgency: Literal["low", "medium", "high"]
    metadata: AIExecutionMetadata
    title_descriptor: MessageDescriptor | None = None
    message_descriptor: MessageDescriptor | None = None


@dataclass(frozen=True, slots=True)
class NotificationCreationResult:
    status: NotificationCreationStatus
    notification_id: int | None = None
    reason: str | None = None
    pending_events: tuple[NotificationPendingEvent, ...] = ()


__all__ = [
    "NotificationCreationResult",
    "NotificationCreationStatus",
    "NotificationHumanizationOutput",
    "NotificationHumanizationResult",
    "NotificationPendingEvent",
]
