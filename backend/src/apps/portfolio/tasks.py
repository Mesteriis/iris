from __future__ import annotations

from src.apps.portfolio.services import PortfolioService, PortfolioSideEffectDispatcher
from src.core.db.uow import AsyncUnitOfWork
from src.runtime.orchestration.broker import broker
from src.runtime.orchestration.locks import async_redis_task_lock

PORTFOLIO_SYNC_LOCK_TIMEOUT_SECONDS = 240


@broker.task
async def portfolio_sync_job() -> dict[str, object]:
    async with async_redis_task_lock("iris:tasklock:portfolio_sync", timeout=PORTFOLIO_SYNC_LOCK_TIMEOUT_SECONDS) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "portfolio_sync_in_progress"}
        async with AsyncUnitOfWork() as uow:
            service = PortfolioService(uow)
            result = await service.sync_exchange_balances(emit_events=True)
            await uow.commit()
        await PortfolioSideEffectDispatcher().apply_sync_result(result)
        return result.to_payload()
