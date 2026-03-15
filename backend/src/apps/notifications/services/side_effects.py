from __future__ import annotations

from src.apps.notifications.contracts import NotificationCreationResult
from src.runtime.streams.publisher import publish_event


class NotificationSideEffectDispatcher:
    async def apply_creation(self, result: NotificationCreationResult) -> None:
        for event in result.pending_events:
            publish_event(event.event_type, dict(event.payload))


__all__ = ["NotificationSideEffectDispatcher"]
