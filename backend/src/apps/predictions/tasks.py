from __future__ import annotations

from src.apps.predictions.services import PredictionService, PredictionSideEffectDispatcher
from src.core.db.uow import AsyncUnitOfWork
from src.runtime.orchestration.broker import analytics_broker
from src.runtime.orchestration.locks import async_redis_task_lock

PREDICTION_EVALUATION_LOCK_TIMEOUT_SECONDS = 300


@analytics_broker.task
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
        return result.to_summary()
