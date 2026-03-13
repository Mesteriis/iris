from __future__ import annotations

from typing import Any

from src.apps.system.api.contracts import HealthRead, SystemStatusRead


def system_status_read(item: Any) -> SystemStatusRead:
    return SystemStatusRead.model_validate(item)


def health_read(*, status: str) -> HealthRead:
    return HealthRead(status=status)


__all__ = ["health_read", "system_status_read"]
