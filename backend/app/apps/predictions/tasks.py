from __future__ import annotations

from app.apps.predictions.services import evaluate_pending_predictions_async
from app.core.db.session import AsyncSessionLocal
from app.runtime.orchestration.broker import analytics_broker
from app.runtime.orchestration.locks import async_redis_task_lock

PREDICTION_EVALUATION_LOCK_TIMEOUT_SECONDS = 300


@analytics_broker.task
async def prediction_evaluation_job() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:prediction_evaluation",
        timeout=PREDICTION_EVALUATION_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "prediction_evaluation_in_progress"}
        async with AsyncSessionLocal() as db:
            return await evaluate_pending_predictions_async(db, emit_events=True)
