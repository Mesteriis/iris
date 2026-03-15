from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis as AsyncRedis

from src.core.errors import PLATFORM_ERROR_REGISTRY, PlatformError
from src.core.http.operations import (
    OperationEventResponse,
    OperationResultResponse,
    OperationStatus,
    OperationStatusResponse,
)
from src.core.http.tracing import TraceContext
from src.core.settings import get_settings

settings = get_settings()

_ACTIVE_OPERATION_STATUSES = frozenset(
    {
        OperationStatus.ACCEPTED,
        OperationStatus.QUEUED,
        OperationStatus.RUNNING,
    }
)
_TERMINAL_OPERATION_STATUSES = frozenset(
    {
        OperationStatus.DEDUPLICATED,
        OperationStatus.SUCCEEDED,
        OperationStatus.FAILED,
        OperationStatus.CANCELLED,
        OperationStatus.REJECTED,
        OperationStatus.TIMED_OUT,
    }
)
_DEFAULT_EVENT_MESSAGE_KEYS: dict[str, str] = {
    "accepted": "system.operation.accepted",
    "queued": "system.operation.queued",
    "running": "system.operation.running",
    "deduplicated": "system.operation.deduplicated",
    "succeeded": "system.operation.succeeded",
    "failed": "system.operation.failed",
    "rejected": "system.operation.rejected",
}

def get_async_operation_client() -> AsyncRedis:
    return AsyncRedis.from_url(settings.redis_url, decode_responses=True)


@dataclass(frozen=True, slots=True)
class OperationDispatchResult:
    operation: OperationStatusResponse
    deduplicated: bool = False
    message_key: str | None = None
    message_params: dict[str, object] | None = None


class OperationStore:
    def __init__(
        self,
        client: AsyncRedis | None = None,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        self._client = client or get_async_operation_client()
        self._ttl_seconds = int(ttl_seconds or settings.api_operation_ttl_seconds)
        self._api_prefix = _build_api_prefix()

    async def create_operation(
        self,
        *,
        operation_type: str,
        trace_context: TraceContext | None = None,
        requested_by: str | None = None,
        deduplication_key: str | None = None,
        operation_id: str | None = None,
    ) -> OperationStatusResponse:
        next_operation_id = operation_id or uuid.uuid4().hex
        trace = trace_context or TraceContext()
        status = OperationStatusResponse(
            operation_id=next_operation_id,
            operation_type=operation_type,
            status=OperationStatus.ACCEPTED,
            accepted_at=_utc_now(),
            correlation_id=trace.correlation_id,
            causation_id=trace.causation_id,
            request_id=trace.request_id,
            requested_by=requested_by,
            deduplication_key=deduplication_key,
        )
        try:
            await self._write_status(status)
            await self._append_event(
                operation_id=next_operation_id,
                operation_type=operation_type,
                event="accepted",
                status=OperationStatus.ACCEPTED,
                message_key=_DEFAULT_EVENT_MESSAGE_KEYS["accepted"],
            )
        except Exception:
            if deduplication_key is not None:
                await self._release_active_deduplication_key(
                    operation_type=operation_type,
                    deduplication_key=deduplication_key,
                    operation_id=next_operation_id,
                )
            raise
        return status

    async def create_or_reuse_active_operation(
        self,
        *,
        operation_type: str,
        trace_context: TraceContext | None = None,
        requested_by: str | None = None,
        deduplication_key: str | None = None,
    ) -> OperationDispatchResult:
        if deduplication_key is None:
            return OperationDispatchResult(
                operation=await self.create_operation(
                    operation_type=operation_type,
                    trace_context=trace_context,
                    requested_by=requested_by,
                )
            )

        for _ in range(3):
            next_operation_id = uuid.uuid4().hex
            claimed, existing = await self._claim_or_get_active_operation(
                operation_type=operation_type,
                deduplication_key=deduplication_key,
                operation_id=next_operation_id,
            )
            if existing is not None:
                return OperationDispatchResult(
                    operation=existing,
                    deduplicated=True,
                    message_key="system.operation.already_active",
                )
            if not claimed:
                continue
            return OperationDispatchResult(
                operation=await self.create_operation(
                    operation_type=operation_type,
                    trace_context=trace_context,
                    requested_by=requested_by,
                    deduplication_key=deduplication_key,
                    operation_id=next_operation_id,
                )
            )
        raise RuntimeError(f"Could not acquire operation slot for '{operation_type}'.")

    async def mark_queued(
        self,
        operation_id: str,
        *,
        message_key: str | None = None,
        message_params: Mapping[str, object] | None = None,
    ) -> OperationStatusResponse:
        return await self._update_status(
            operation_id,
            status=OperationStatus.QUEUED,
            event="queued",
            message_key=message_key or _DEFAULT_EVENT_MESSAGE_KEYS["queued"],
            message_params=message_params,
        )

    async def mark_running(
        self,
        operation_id: str,
        *,
        message_key: str | None = None,
        message_params: Mapping[str, object] | None = None,
    ) -> OperationStatusResponse:
        return await self._update_status(
            operation_id,
            status=OperationStatus.RUNNING,
            event="running",
            message_key=message_key or _DEFAULT_EVENT_MESSAGE_KEYS["running"],
            message_params=message_params,
            started_at=_utc_now(),
        )

    async def mark_deduplicated(
        self,
        operation_id: str,
        *,
        message_key: str | None = None,
        message_params: Mapping[str, object] | None = None,
        result: Mapping[str, object] | None = None,
    ) -> OperationStatusResponse:
        status = await self._update_status(
            operation_id,
            status=OperationStatus.DEDUPLICATED,
            event="deduplicated",
            message_key=message_key or _DEFAULT_EVENT_MESSAGE_KEYS["deduplicated"],
            message_params=message_params,
            finished_at=_utc_now(),
            result_ref=self._result_path(operation_id),
        )
        if result is not None:
            await self._write_result(operation_id, result)
        return status

    async def mark_succeeded(
        self,
        operation_id: str,
        *,
        message_key: str | None = None,
        message_params: Mapping[str, object] | None = None,
        result: Mapping[str, object] | None = None,
    ) -> OperationStatusResponse:
        status = await self._update_status(
            operation_id,
            status=OperationStatus.SUCCEEDED,
            event="succeeded",
            message_key=message_key or _DEFAULT_EVENT_MESSAGE_KEYS["succeeded"],
            message_params=message_params,
            finished_at=_utc_now(),
            result_ref=self._result_path(operation_id),
        )
        if result is not None:
            await self._write_result(operation_id, result)
        return status

    async def mark_failed(
        self,
        operation_id: str,
        *,
        error_code: str,
        error_message_key: str,
        error_message_params: Mapping[str, object] | None = None,
        retryable: bool,
        result: Mapping[str, object] | None = None,
    ) -> OperationStatusResponse:
        status = await self._update_status(
            operation_id,
            status=OperationStatus.FAILED,
            event="failed",
            message_key=_DEFAULT_EVENT_MESSAGE_KEYS["failed"],
            finished_at=_utc_now(),
            result_ref=self._result_path(operation_id),
            error_code=error_code,
            error_message_key=error_message_key,
            error_message_params=dict(error_message_params or {}),
            retryable=retryable,
        )
        if result is not None:
            await self._write_result(operation_id, result)
        return status

    async def mark_rejected(
        self,
        operation_id: str,
        *,
        error_code: str,
        error_message_key: str,
        error_message_params: Mapping[str, object] | None = None,
        retryable: bool,
    ) -> OperationStatusResponse:
        return await self._update_status(
            operation_id,
            status=OperationStatus.REJECTED,
            event="rejected",
            message_key=_DEFAULT_EVENT_MESSAGE_KEYS["rejected"],
            finished_at=_utc_now(),
            error_code=error_code,
            error_message_key=error_message_key,
            error_message_params=dict(error_message_params or {}),
            retryable=retryable,
        )

    async def get_status(self, operation_id: str) -> OperationStatusResponse | None:
        raw = await self._client.get(self._status_key(operation_id))
        if raw is None:
            return None
        return OperationStatusResponse.model_validate(json.loads(raw))

    async def get_result(self, operation_id: str) -> OperationResultResponse | None:
        status = await self.get_status(operation_id)
        if status is None:
            return None
        raw = await self._client.get(self._result_key(operation_id))
        result = json.loads(raw) if raw is not None else None
        return OperationResultResponse.model_validate(
            {
                **status.model_dump(mode="json"),
                "result": result,
            }
        )

    async def list_events(self, operation_id: str) -> tuple[OperationEventResponse, ...]:
        raw_events = await self._client.lrange(self._events_key(operation_id), 0, -1)
        return tuple(
            OperationEventResponse.model_validate(json.loads(raw_event))
            for raw_event in raw_events
        )

    async def _update_status(
        self,
        operation_id: str,
        *,
        status: OperationStatus,
        event: str,
        message_key: str | None = None,
        message_params: Mapping[str, object] | None = None,
        **updates: object,
    ) -> OperationStatusResponse:
        current = await self.get_status(operation_id)
        if current is None:
            raise KeyError(f"Operation '{operation_id}' was not found.")
        next_status = current.model_copy(update={"status": status, **updates})
        await self._write_status(next_status)
        if next_status.deduplication_key is not None:
            if status in _ACTIVE_OPERATION_STATUSES:
                await self._refresh_active_deduplication_key(
                    operation_type=next_status.operation_type,
                    deduplication_key=next_status.deduplication_key,
                    operation_id=next_status.operation_id,
                )
            elif status in _TERMINAL_OPERATION_STATUSES:
                await self._release_active_deduplication_key(
                    operation_type=next_status.operation_type,
                    deduplication_key=next_status.deduplication_key,
                    operation_id=next_status.operation_id,
                )
        await self._append_event(
            operation_id=next_status.operation_id,
            operation_type=next_status.operation_type,
            event=event,
            status=status,
            message_key=message_key,
            message_params=message_params,
            payload={key: value for key, value in updates.items() if value is not None},
        )
        return next_status

    async def _write_status(self, status: OperationStatusResponse) -> None:
        await self._client.set(
            self._status_key(status.operation_id),
            json.dumps(status.model_dump(mode="json"), sort_keys=True),
            ex=self._ttl_seconds,
        )

    async def _write_result(self, operation_id: str, result: Mapping[str, object]) -> None:
        await self._client.set(
            self._result_key(operation_id),
            json.dumps(dict(result), sort_keys=True, default=str),
            ex=self._ttl_seconds,
        )

    async def _append_event(
        self,
        *,
        operation_id: str,
        operation_type: str,
        event: str,
        status: OperationStatus,
        message_key: str | None = None,
        message_params: Mapping[str, object] | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        item = OperationEventResponse(
            operation_id=operation_id,
            operation_type=operation_type,
            event=event,
            status=status,
            recorded_at=_utc_now(),
            message_key=message_key,
            message_params=dict(message_params or {}),
            payload=dict(payload) if payload is not None else None,
        )
        async with self._client.pipeline(transaction=False) as pipeline:
            pipeline.rpush(
                self._events_key(operation_id),
                json.dumps(item.model_dump(mode="json"), sort_keys=True),
            )
            pipeline.expire(self._events_key(operation_id), self._ttl_seconds)
            await pipeline.execute()

    def _status_key(self, operation_id: str) -> str:
        return f"iris:http:operations:{operation_id}:status"

    def _result_key(self, operation_id: str) -> str:
        return f"iris:http:operations:{operation_id}:result"

    def _events_key(self, operation_id: str) -> str:
        return f"iris:http:operations:{operation_id}:events"

    def _deduplication_slot_key(self, operation_type: str, deduplication_key: str) -> str:
        return f"iris:http:operations:dedup:{operation_type}:{deduplication_key}"

    def _result_path(self, operation_id: str) -> str:
        return f"{self._api_prefix}/operations/{operation_id}/result"

    async def _claim_or_get_active_operation(
        self,
        *,
        operation_type: str,
        deduplication_key: str,
        operation_id: str,
    ) -> tuple[bool, OperationStatusResponse | None]:
        key = self._deduplication_slot_key(operation_type, deduplication_key)
        claimed = await self._client.set(key, operation_id, ex=self._ttl_seconds, nx=True)
        if claimed:
            return True, None
        active_operation_id = await self._client.get(key)
        if active_operation_id is None:
            return False, None
        active_status = await self.get_status(active_operation_id)
        if active_status is not None and active_status.status in _ACTIVE_OPERATION_STATUSES:
            return False, active_status
        await self._delete_key_if_matches(key=key, expected_value=active_operation_id)
        return False, None

    async def _refresh_active_deduplication_key(
        self,
        *,
        operation_type: str,
        deduplication_key: str,
        operation_id: str,
    ) -> None:
        key = self._deduplication_slot_key(operation_type, deduplication_key)
        if await self._client.get(key) == operation_id:
            await self._client.expire(key, self._ttl_seconds)

    async def _release_active_deduplication_key(
        self,
        *,
        operation_type: str,
        deduplication_key: str,
        operation_id: str,
    ) -> None:
        key = self._deduplication_slot_key(operation_type, deduplication_key)
        await self._delete_key_if_matches(key=key, expected_value=operation_id)

    async def _delete_key_if_matches(self, *, key: str, expected_value: str) -> None:
        if await self._client.get(key) == expected_value:
            await self._client.delete(key)


async def dispatch_background_operation(
    *,
    store: OperationStore,
    operation_type: str,
    dispatch: Callable[[str], Awaitable[None]],
    trace_context: TraceContext | None = None,
    requested_by: str | None = None,
    deduplication_key: str | None = None,
) -> OperationDispatchResult:
    dispatch_result = await store.create_or_reuse_active_operation(
        operation_type=operation_type,
        trace_context=trace_context,
        requested_by=requested_by,
        deduplication_key=deduplication_key,
    )
    operation = dispatch_result.operation
    if dispatch_result.deduplicated:
        return dispatch_result
    try:
        await dispatch(operation.operation_id)
    except Exception as exc:
        error_code, error_message_key, error_message_params, retryable = _operation_error_from_exception(
            exc,
            fallback_code="dispatch_failed",
            fallback_message_key=_DEFAULT_EVENT_MESSAGE_KEYS["rejected"],
            fallback_retryable=True,
        )
        await store.mark_rejected(
            operation.operation_id,
            error_code=error_code,
            error_message_key=error_message_key,
            error_message_params=error_message_params,
            retryable=retryable,
        )
        raise
    queued_operation = await store.mark_queued(operation.operation_id)
    return OperationDispatchResult(operation=queued_operation)


async def run_tracked_operation(
    *,
    store: OperationStore,
    operation_id: str | None,
    action: Callable[[], Awaitable[dict[str, object]]],
) -> dict[str, object]:
    if operation_id is None:
        return await action()
    await store.mark_running(operation_id)
    try:
        result = await action()
    except Exception as exc:
        error_code, error_message_key, error_message_params, retryable = _operation_error_from_exception(
            exc,
            fallback_code="task_failed",
            fallback_message_key=_DEFAULT_EVENT_MESSAGE_KEYS["failed"],
            fallback_retryable=True,
        )
        await store.mark_failed(
            operation_id,
            error_code=error_code,
            error_message_key=error_message_key,
            error_message_params=error_message_params,
            retryable=retryable,
        )
        raise
    status = str(result.get("status", "ok")).strip().lower()
    if status in {"skipped", "deduplicated"}:
        await store.mark_deduplicated(
            operation_id,
            message_key=_DEFAULT_EVENT_MESSAGE_KEYS["deduplicated"],
            result=result,
        )
        return result
    if status in {"error", "failed", "rejected"}:
        error_code, error_message_key, error_message_params, retryable = _operation_error_from_result(result)
        await store.mark_failed(
            operation_id,
            error_code=error_code,
            error_message_key=error_message_key,
            error_message_params=error_message_params,
            retryable=retryable,
            result=result,
        )
        return result
    await store.mark_succeeded(operation_id, result=result)
    return result


def _build_api_prefix() -> str:
    root = settings.api_root_prefix.rstrip("/")
    version = settings.api_version_prefix.rstrip("/")
    return f"{root}{version}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _operation_error_from_exception(
    exc: Exception,
    *,
    fallback_code: str,
    fallback_message_key: str,
    fallback_retryable: bool,
) -> tuple[str, str, dict[str, object], bool]:
    if isinstance(exc, PlatformError):
        return exc.code, exc.message_key, dict(exc.params), exc.retryable
    return fallback_code, fallback_message_key, {}, fallback_retryable


def _operation_error_from_result(result: Mapping[str, object]) -> tuple[str, str, dict[str, object], bool]:
    error_code = str(result.get("error_code") or result.get("reason") or "task_failed")
    if error_code in PLATFORM_ERROR_REGISTRY:
        definition = PLATFORM_ERROR_REGISTRY.get(error_code)
        return error_code, definition.message_key, dict(_normalize_message_params(result.get("message_params"))), bool(
            result.get("retryable", definition.retryable)
        )
    message_key = result.get("message_key")
    if isinstance(message_key, str) and message_key.strip():
        return error_code, message_key, dict(_normalize_message_params(result.get("message_params"))), bool(
            result.get("retryable", False)
        )
    return error_code, _DEFAULT_EVENT_MESSAGE_KEYS["failed"], {}, bool(result.get("retryable", False))


def _normalize_message_params(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


__all__ = [
    "OperationDispatchResult",
    "OperationStore",
    "dispatch_background_operation",
    "get_async_operation_client",
    "run_tracked_operation",
]
