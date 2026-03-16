from collections.abc import Callable
from typing import cast

from iris.apps.predictions.services import PredictionService, PredictionSideEffectDispatcher
from iris.core.db.uow import AsyncUnitOfWork
from iris.runtime.orchestration.broker import analytics_broker
from iris.runtime.orchestration.locks import async_redis_task_lock

PREDICTION_EVALUATION_LOCK_TIMEOUT_SECONDS = 300


def _analytics_task[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    return cast(Callable[P, R], analytics_broker.task(func))


@_analytics_task
async def prediction_evaluation_job() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:prediction_evaluation",
        timeout=PREDICTION_EVALUATION_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "prediction_evaluation_in_progress"}
        async with AsyncUnitOfWork() as uow:
            result = await PredictionService(uow).evaluate_pending_predictions(emit_events=True)
            await uow.commit()
        await PredictionSideEffectDispatcher().apply_evaluation(result)
        return {
            "status": result.status,
            "evaluated": int(result.evaluated),
            "confirmed": int(result.confirmed),
            "failed": int(result.failed),
            "expired": int(result.expired),
        }
