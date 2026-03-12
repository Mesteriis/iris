from __future__ import annotations

from src.apps.news.services import NewsService
from src.core.db.session import AsyncSessionLocal
from src.runtime.orchestration.broker import broker
from src.runtime.orchestration.locks import async_redis_task_lock

NEWS_SOURCE_POLL_LOCK_TIMEOUT_SECONDS = 120
NEWS_ENABLED_POLL_LOCK_TIMEOUT_SECONDS = 300


@broker.task
async def poll_news_source_job(source_id: int, limit: int = 50) -> dict[str, object]:
    async with async_redis_task_lock(
        f"iris:tasklock:news_source_poll:{int(source_id)}",
        timeout=NEWS_SOURCE_POLL_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "news_source_poll_in_progress", "source_id": int(source_id)}
        async with AsyncSessionLocal() as db:
            return await NewsService(db).poll_source(source_id=int(source_id), limit=int(limit))


@broker.task
async def poll_enabled_news_sources_job(limit_per_source: int = 50) -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:news_enabled_poll",
        timeout=NEWS_ENABLED_POLL_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "news_enabled_poll_in_progress"}
        async with AsyncSessionLocal() as db:
            return await NewsService(db).poll_enabled_sources(limit_per_source=int(limit_per_source))
