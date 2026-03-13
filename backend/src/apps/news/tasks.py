from __future__ import annotations

from src.apps.news.query_services import NewsQueryService
from src.apps.news.services import NewsService
from src.core.db.uow import AsyncUnitOfWork
from src.core.http.operation_store import OperationStore, run_tracked_operation
from src.runtime.orchestration.broker import broker
from src.runtime.orchestration.locks import async_redis_task_lock

NEWS_SOURCE_POLL_LOCK_TIMEOUT_SECONDS = 120
NEWS_ENABLED_POLL_LOCK_TIMEOUT_SECONDS = 300


@broker.task
async def poll_news_source_job(
    source_id: int,
    limit: int = 50,
    operation_id: str | None = None,
) -> dict[str, object]:
    async def _action() -> dict[str, object]:
        async with async_redis_task_lock(
            f"iris:tasklock:news_source_poll:{int(source_id)}",
            timeout=NEWS_SOURCE_POLL_LOCK_TIMEOUT_SECONDS,
        ) as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "news_source_poll_in_progress", "source_id": int(source_id)}
            async with AsyncUnitOfWork() as uow:
                result = await NewsService(uow).poll_source(source_id=int(source_id), limit=int(limit))
                await uow.commit()
                return result

    return await run_tracked_operation(
        store=OperationStore(),
        operation_id=operation_id,
        action=_action,
    )


@broker.task
async def poll_enabled_news_sources_job(limit_per_source: int = 50) -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:news_enabled_poll",
        timeout=NEWS_ENABLED_POLL_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "news_enabled_poll_in_progress"}
        async with AsyncUnitOfWork() as uow:
            source_ids = [
                int(item.id)
                for item in await NewsQueryService(uow.session).list_sources()
                if bool(item.enabled)
            ]
        items: list[dict[str, object]] = []
        for source_id in source_ids:
            async with AsyncUnitOfWork() as uow:
                items.append(await NewsService(uow).poll_source(source_id=source_id, limit=int(limit_per_source)))
                await uow.commit()
        return {
            "status": "ok",
            "sources": len(source_ids),
            "items": items,
            "created": sum(int(item.get("created", 0)) for item in items),
        }
