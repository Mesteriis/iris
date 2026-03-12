from __future__ import annotations

from src.apps.hypothesis_engine.services import EvaluationService
from src.apps.market_data.domain import utc_now
from src.core.db.session import AsyncSessionLocal
from src.runtime.orchestration.broker import analytics_broker
from src.runtime.orchestration.locks import async_redis_task_lock

HYPOTHESIS_EVALUATION_LOCK_TIMEOUT_SECONDS = 300


@analytics_broker.task
async def evaluate_hypotheses_job() -> dict[str, object]:
    async with async_redis_task_lock(
        "iris:tasklock:hypothesis_evaluation",
        timeout=HYPOTHESIS_EVALUATION_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "hypothesis_evaluation_in_progress"}
        async with AsyncSessionLocal() as db:
            eval_ids = await EvaluationService(db).evaluate_due(utc_now())
            return {"status": "ok", "evaluated": len(eval_ids), "evaluation_ids": eval_ids}
