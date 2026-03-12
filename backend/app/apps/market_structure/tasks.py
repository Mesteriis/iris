from __future__ import annotations

from app.apps.market_structure.services import MarketStructureService
from app.core.db.session import AsyncSessionLocal
from app.runtime.orchestration.broker import broker
from app.runtime.orchestration.locks import async_redis_task_lock

MARKET_STRUCTURE_SOURCE_POLL_LOCK_TIMEOUT_SECONDS = 120
MARKET_STRUCTURE_ENABLED_POLL_LOCK_TIMEOUT_SECONDS = 300
MARKET_STRUCTURE_HEALTH_REFRESH_LOCK_TIMEOUT_SECONDS = 180


@broker.task
async def poll_market_structure_source_job(source_id: int, limit: int = 1) -> dict[str, object]:
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
        async with AsyncSessionLocal() as db:
            return await MarketStructureService(db).poll_source(source_id=int(source_id), limit=int(limit))


@broker.task
async def poll_enabled_market_structure_sources_job(limit_per_source: int = 1) -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:market_structure_enabled_poll",
        timeout=MARKET_STRUCTURE_ENABLED_POLL_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "market_structure_enabled_poll_in_progress"}
        async with AsyncSessionLocal() as db:
            return await MarketStructureService(db).poll_enabled_sources(limit_per_source=int(limit_per_source))


@broker.task
async def refresh_market_structure_source_health_job() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:market_structure_health_refresh",
        timeout=MARKET_STRUCTURE_HEALTH_REFRESH_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "market_structure_health_refresh_in_progress"}
        async with AsyncSessionLocal() as db:
            return await MarketStructureService(db).refresh_source_health(emit_events=True)
