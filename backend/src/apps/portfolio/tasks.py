from __future__ import annotations

from src.apps.portfolio.serializers import portfolio_sync_result_payload
from src.apps.portfolio.services import PortfolioService, PortfolioSideEffectDispatcher
from src.core.db.uow import AsyncUnitOfWork
from src.core.http.operation_store import OperationStore, run_tracked_operation
from src.runtime.orchestration.broker import broker
from src.runtime.orchestration.locks import async_redis_task_lock

PORTFOLIO_SYNC_LOCK_TIMEOUT_SECONDS = 240


@broker.task
async def portfolio_sync_job(operation_id: str | None = None) -> dict[str, object]:
    async def _action() -> dict[str, object]:
        async with async_redis_task_lock("iris:tasklock:portfolio_sync", timeout=PORTFOLIO_SYNC_LOCK_TIMEOUT_SECONDS) as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "portfolio_sync_in_progress"}
            async with AsyncUnitOfWork() as uow:
                service = PortfolioService(uow)
                result = await service.sync_exchange_balances(emit_events=True)
                await uow.commit()
            await PortfolioSideEffectDispatcher().apply_sync_result(result)
            return portfolio_sync_result_payload(result)

    return await run_tracked_operation(
        store=OperationStore(),
        operation_id=operation_id,
        action=_action,
    )
