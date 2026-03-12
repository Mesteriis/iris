from __future__ import annotations

from app.core.db.session import AsyncSessionLocal
from app.apps.portfolio.services import sync_exchange_balances_async
from app.runtime.orchestration.broker import broker
from app.runtime.orchestration.locks import async_redis_task_lock

PORTFOLIO_SYNC_LOCK_TIMEOUT_SECONDS = 240


@broker.task
async def portfolio_sync_job() -> dict[str, object]:
    async with async_redis_task_lock("iris:tasklock:portfolio_sync", timeout=PORTFOLIO_SYNC_LOCK_TIMEOUT_SECONDS) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "portfolio_sync_in_progress"}
        async with AsyncSessionLocal() as db:
            return await sync_exchange_balances_async(db, emit_events=True)
