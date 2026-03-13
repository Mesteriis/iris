from __future__ import annotations

from typing import Any

from datetime import datetime
from enum import StrEnum

from src.core.http.contracts import HttpContract


class OperationStatus(StrEnum):
    ACCEPTED = "accepted"
    DEDUPLICATED = "deduplicated"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


class OperationResponse(HttpContract):
    operation_id: str
    operation_type: str
    status: OperationStatus
    accepted_at: datetime
    correlation_id: str | None = None
    causation_id: str | None = None
    request_id: str | None = None


class OperationStatusResponse(OperationResponse):
    requested_by: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    deduplication_key: str | None = None
    result_ref: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False


class OperationResultResponse(OperationStatusResponse):
    result: dict[str, Any] | None = None


class OperationEventResponse(HttpContract):
    operation_id: str
    operation_type: str
    event: str
    status: OperationStatus
    recorded_at: datetime
    message: str | None = None
    payload: dict[str, Any] | None = None
