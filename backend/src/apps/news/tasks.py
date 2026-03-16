from collections.abc import Mapping

from src.apps.news.query_services import NewsQueryService
from src.apps.news.results import NewsEnabledPollResult, NewsSourcePollResult
from src.apps.news.services import NewsService
from src.core.db.uow import AsyncUnitOfWork
from src.core.http.operation_store import OperationStore, run_tracked_operation
from src.runtime.orchestration.broker import broker
from src.runtime.orchestration.locks import async_redis_task_lock

NEWS_SOURCE_POLL_LOCK_TIMEOUT_SECONDS = 120
NEWS_ENABLED_POLL_LOCK_TIMEOUT_SECONDS = 300


def _serialize_source_poll_result(result: NewsSourcePollResult | Mapping[str, object]) -> dict[str, object]:
    if isinstance(result, Mapping):
        return dict(result)

    payload: dict[str, object] = {
        "status": result.status,
        "source_id": int(result.source_id),
        "created": int(result.created),
    }
    if result.plugin_name is not None:
        payload["plugin_name"] = result.plugin_name
    if result.fetched:
        payload["fetched"] = int(result.fetched)
    if result.cursor:
        payload["cursor"] = dict(result.cursor)
    if result.reason is not None:
        payload["reason"] = result.reason
    if result.error is not None:
        payload["error"] = result.error
    return payload


def _serialize_enabled_poll_result(result: NewsEnabledPollResult | Mapping[str, object]) -> dict[str, object]:
    if isinstance(result, Mapping):
        return dict(result)
    return {
        "status": result.status,
        "sources": int(result.sources),
        "created": int(result.created),
        "items": [_serialize_source_poll_result(item) for item in result.items],
    }


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
                return _serialize_source_poll_result(result)

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
            source_ids = [int(item.id) for item in await NewsQueryService(uow.session).list_sources() if bool(item.enabled)]
            result = await NewsService(uow).poll_enabled_sources(limit_per_source=int(limit_per_source))
            await uow.commit()
            payload = _serialize_enabled_poll_result(result)
            payload["sources"] = len(source_ids)
            return payload
