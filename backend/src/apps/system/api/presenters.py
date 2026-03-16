from typing import Any

from src.apps.system.api.contracts import (
    HealthRead,
    OperationEventResponse,
    OperationResultResponse,
    OperationStatusResponse,
    SystemStatusRead,
)
from src.core.http.operation_localization import (
    localize_operation_event,
    localize_operation_result,
    localize_operation_status,
)


def system_status_read(item: Any) -> SystemStatusRead:
    return SystemStatusRead.model_validate(item)


def health_read(*, status: str) -> HealthRead:
    return HealthRead(status=status)


def operation_status_read(item: Any, *, locale: str | None = None) -> OperationStatusResponse:
    return localize_operation_status(item, locale=locale)


def operation_result_read(item: Any, *, locale: str | None = None) -> OperationResultResponse:
    return localize_operation_result(item, locale=locale)


def operation_event_read(item: Any, *, locale: str | None = None) -> OperationEventResponse:
    return localize_operation_event(item, locale=locale)


__all__ = [
    "health_read",
    "operation_event_read",
    "operation_result_read",
    "operation_status_read",
    "system_status_read",
]
