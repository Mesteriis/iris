from collections.abc import Callable
from typing import ParamSpec, TypeVar, cast

from iris.apps.market_structure.query_services import MarketStructureQueryService
from iris.apps.market_structure.services import (
    MarketStructureService,
    serialize_market_structure_poll_source_result,
    serialize_market_structure_refresh_result,
)
from iris.core.db.uow import AsyncUnitOfWork
from iris.core.http.operation_store import OperationStore, run_tracked_operation
from iris.runtime.orchestration.broker import broker
from iris.runtime.orchestration.locks import async_redis_task_lock

P = ParamSpec("P")
R = TypeVar("R")

MARKET_STRUCTURE_SOURCE_POLL_LOCK_TIMEOUT_SECONDS = 120
MARKET_STRUCTURE_ENABLED_POLL_LOCK_TIMEOUT_SECONDS = 300
MARKET_STRUCTURE_HEALTH_REFRESH_LOCK_TIMEOUT_SECONDS = 180


def _int_value(value: object) -> int:
    return int(cast(int | str | bytes | bytearray, value))


def _task[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    return cast(Callable[P, R], broker.task(func))


@_task
async def poll_market_structure_source_job(
    source_id: int,
    limit: int = 1,
    operation_id: str | None = None,
) -> dict[str, object]:
    async def _action() -> dict[str, object]:
        async with async_redis_task_lock(
            f"iris:tasklock:market_structure_source_poll:{int(source_id)}",
            timeout=MARKET_STRUCTURE_SOURCE_POLL_LOCK_TIMEOUT_SECONDS,
        ) as acquired:
            if not acquired:
                return {
                    "status": "skipped",
                    "reason": "market_structure_source_poll_in_progress",
                    "source_id": int(source_id),
                }
            async with AsyncUnitOfWork() as uow:
                result = await MarketStructureService(uow).poll_source(source_id=int(source_id), limit=int(limit))
                await uow.commit()
                return serialize_market_structure_poll_source_result(result)

    return await run_tracked_operation(
        store=OperationStore(),
        operation_id=operation_id,
        action=_action,
    )


@_task
async def poll_enabled_market_structure_sources_job(limit_per_source: int = 1) -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:market_structure_enabled_poll",
        timeout=MARKET_STRUCTURE_ENABLED_POLL_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "market_structure_enabled_poll_in_progress"}
        async with AsyncUnitOfWork() as uow:
            source_ids = await MarketStructureQueryService(uow.session).list_enabled_source_ids()

        items: list[dict[str, object]] = []
        for source_id in source_ids:
            async with AsyncUnitOfWork() as uow:
                item = await MarketStructureService(uow).poll_source(
                    source_id=int(source_id),
                    limit=int(limit_per_source),
                )
                await uow.commit()
                items.append(serialize_market_structure_poll_source_result(item))
        return {
            "status": "ok",
            "sources": len(source_ids),
            "items": items,
            "created": sum(_int_value(item.get("created") or 0) for item in items),
        }


@_task
async def refresh_market_structure_source_health_job(
    operation_id: str | None = None,
) -> dict[str, object]:
    async def _action() -> dict[str, object]:
        async with async_redis_task_lock(
            "iris:tasklock:market_structure_health_refresh",
            timeout=MARKET_STRUCTURE_HEALTH_REFRESH_LOCK_TIMEOUT_SECONDS,
        ) as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "market_structure_health_refresh_in_progress"}
            async with AsyncUnitOfWork() as uow:
                result = await MarketStructureService(uow).refresh_source_health(emit_events=True)
                await uow.commit()
                return serialize_market_structure_refresh_result(result)

    return await run_tracked_operation(
        store=OperationStore(),
        operation_id=operation_id,
        action=_action,
    )
