from __future__ import annotations

from src.core.db.session import AsyncSessionLocal
from src.apps.portfolio.services import sync_exchange_balances_async
from src.runtime.orchestration.broker import broker
from src.runtime.orchestration.locks import async_redis_task_lock

PORTFOLIO_SYNC_LOCK_TIMEOUT_SECONDS = 240


@broker.task
async def portfolio_sync_job() -> dict[str, object]:
    async with async_redis_task_lock("iris:tasklock:portfolio_sync", timeout=PORTFOLIO_SYNC_LOCK_TIMEOUT_SECONDS) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "portfolio_sync_in_progress"}
        async with AsyncSessionLocal() as db:
            return await sync_exchange_balances_async(db, emit_events=True)
