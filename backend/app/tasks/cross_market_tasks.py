from __future__ import annotations

from app.analysis.prediction_memory_engine import evaluate_pending_predictions
from app.db.session import SessionLocal
from app.taskiq.broker import broker
from app.taskiq.locks import redis_task_lock

PREDICTION_EVALUATION_LOCK_TIMEOUT_SECONDS = 300


@broker.task
def prediction_evaluation_job() -> dict[str, object]:
    with redis_task_lock(
        "iris:tasklock:prediction_evaluation",
        timeout=PREDICTION_EVALUATION_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "prediction_evaluation_in_progress"}
        db = SessionLocal()
        try:
            return evaluate_pending_predictions(db, emit_events=True)
        finally:
            db.close()
