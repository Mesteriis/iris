from __future__ import annotations

import pytest
from redis.asyncio import Redis as AsyncRedis

from src.core.http.operation_store import OperationStore, dispatch_background_operation, run_tracked_operation
from src.core.http.operations import OperationStatus
from src.core.http.tracing import TraceContext
from src.core.settings import get_settings


@pytest.mark.asyncio
async def test_operation_store_tracks_status_and_events() -> None:
    settings = get_settings()
    client = AsyncRedis.from_url(settings.redis_url, decode_responses=True)
    store = OperationStore(client=client, ttl_seconds=60)
    try:
        created = await store.create_operation(
            operation_type="test.operation",
            trace_context=TraceContext(request_id="req-1", correlation_id="corr-1", causation_id="cause-1"),
        )
        queued = await store.mark_queued(created.operation_id)

        status = await store.get_status(created.operation_id)
        result = await store.get_result(created.operation_id)
        events = await store.list_events(created.operation_id)

        assert queued.status is OperationStatus.QUEUED
        assert status is not None
        assert status.status is OperationStatus.QUEUED
        assert status.request_id == "req-1"
        assert result is not None
        assert result.result is None
        assert [item.event for item in events] == ["accepted", "queued"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_run_tracked_operation_records_terminal_states() -> None:
    settings = get_settings()
    client = AsyncRedis.from_url(settings.redis_url, decode_responses=True)
    store = OperationStore(client=client, ttl_seconds=60)
    try:
        success = await store.create_operation(operation_type="test.success")
        await store.mark_queued(success.operation_id)

        payload = await run_tracked_operation(
            store=store,
            operation_id=success.operation_id,
            action=lambda: _return_result({"status": "ok", "created": 2}),
        )
        success_status = await store.get_result(success.operation_id)
        success_events = await store.list_events(success.operation_id)

        deduplicated = await store.create_operation(operation_type="test.deduplicated")
        await store.mark_queued(deduplicated.operation_id)

        skipped_payload = await run_tracked_operation(
            store=store,
            operation_id=deduplicated.operation_id,
            action=lambda: _return_result({"status": "skipped", "reason": "already_running"}),
        )
        deduplicated_status = await store.get_result(deduplicated.operation_id)

        assert payload["created"] == 2
        assert success_status is not None
        assert success_status.status is OperationStatus.SUCCEEDED
        assert success_status.result == {"status": "ok", "created": 2}
        assert [item.event for item in success_events] == ["accepted", "queued", "running", "succeeded"]

        assert skipped_payload["reason"] == "already_running"
        assert deduplicated_status is not None
        assert deduplicated_status.status is OperationStatus.DEDUPLICATED
        assert deduplicated_status.result == {"status": "skipped", "reason": "already_running"}
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_dispatch_background_operation_deduplicates_active_jobs() -> None:
    settings = get_settings()
    client = AsyncRedis.from_url(settings.redis_url, decode_responses=True)
    store = OperationStore(client=client, ttl_seconds=60)
    dispatched: list[str] = []
    try:
        first = await dispatch_background_operation(
            store=store,
            operation_type="test.job",
            deduplication_key="resource:1",
            dispatch=lambda operation_id: _record_dispatch(dispatched, operation_id),
        )
        second = await dispatch_background_operation(
            store=store,
            operation_type="test.job",
            deduplication_key="resource:1",
            dispatch=lambda operation_id: _record_dispatch(dispatched, operation_id),
        )

        assert first.deduplicated is False
        assert second.deduplicated is True
        assert second.message == "An equivalent operation is already active."
        assert first.operation.operation_id == second.operation.operation_id
        assert dispatched == [first.operation.operation_id]

        await store.mark_failed(
            first.operation.operation_id,
            error_code="task_failed",
            error_message="boom",
            retryable=False,
        )

        third = await dispatch_background_operation(
            store=store,
            operation_type="test.job",
            deduplication_key="resource:1",
            dispatch=lambda operation_id: _record_dispatch(dispatched, operation_id),
        )
        assert third.deduplicated is False
        assert third.operation.operation_id != first.operation.operation_id
        assert dispatched == [first.operation.operation_id, third.operation.operation_id]
    finally:
        await client.aclose()


async def _return_result(payload: dict[str, object]) -> dict[str, object]:
    return payload


async def _record_dispatch(dispatched: list[str], operation_id: str) -> None:
    dispatched.append(operation_id)
