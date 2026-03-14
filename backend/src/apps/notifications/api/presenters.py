from __future__ import annotations

from typing import Any

from src.apps.notifications.api.contracts import NotificationRead


def notification_read(item: Any) -> NotificationRead:
    return NotificationRead.model_validate(item)


__all__ = ["notification_read"]
