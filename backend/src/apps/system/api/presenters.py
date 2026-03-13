from __future__ import annotations

from typing import Any

from src.apps.system.api.contracts import (
    HealthRead,
    OperationEventResponse,
    OperationResultResponse,
    OperationStatusResponse,
    SystemStatusRead,
)


def system_status_read(item: Any) -> SystemStatusRead:
    return SystemStatusRead.model_validate(item)


def health_read(*, status: str) -> HealthRead:
    return HealthRead(status=status)


def operation_status_read(item: Any) -> OperationStatusResponse:
    return OperationStatusResponse.model_validate(item)


def operation_result_read(item: Any) -> OperationResultResponse:
    return OperationResultResponse.model_validate(item)


def operation_event_read(item: Any) -> OperationEventResponse:
    return OperationEventResponse.model_validate(item)


__all__ = [
    "health_read",
    "operation_event_read",
    "operation_result_read",
    "operation_status_read",
    "system_status_read",
]
