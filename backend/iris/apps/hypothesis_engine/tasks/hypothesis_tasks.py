from iris.apps.hypothesis_engine.services import EvaluationService, HypothesisSideEffectDispatcher
from iris.apps.market_data.domain import utc_now
from iris.core.db.uow import AsyncUnitOfWork
from iris.core.http.operation_store import OperationStore, run_tracked_operation
from iris.runtime.orchestration.broker import analytics_broker
from iris.runtime.orchestration.locks import async_redis_task_lock

HYPOTHESIS_EVALUATION_LOCK_TIMEOUT_SECONDS = 300


@analytics_broker.task
async def evaluate_hypotheses_job(
    operation_id: str | None = None,
) -> dict[str, object]:
    async def _action() -> dict[str, object]:
        async with async_redis_task_lock(
            "iris:tasklock:hypothesis_evaluation",
            timeout=HYPOTHESIS_EVALUATION_LOCK_TIMEOUT_SECONDS,
        ) as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "hypothesis_evaluation_in_progress"}
            async with AsyncUnitOfWork() as uow:
                result = await EvaluationService(uow).evaluate_due(utc_now())
                await uow.commit()
            await HypothesisSideEffectDispatcher().apply_evaluation_batch(result)
            return {
                "status": "ok",
                "evaluated": len(result.evaluation_ids),
                "evaluation_ids": list(result.evaluation_ids),
            }

    return await run_tracked_operation(
        store=OperationStore(),
        operation_id=operation_id,
        action=_action,
    )
