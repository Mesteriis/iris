from __future__ import annotations

from app.db.session import SessionLocal
from app.services.metrics_service import update_coin_metrics as update_coin_metrics_service
from app.taskiq.broker import broker
from app.taskiq.locks import redis_task_lock

COIN_METRICS_LOCK_TIMEOUT_SECONDS = 900


@broker.task
def update_coin_metrics() -> dict[str, object]:
    with redis_task_lock(
        "iris:tasklock:coin_metrics_refresh",
        timeout=COIN_METRICS_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {
                "status": "skipped",
                "reason": "coin_metrics_refresh_in_progress",
            }

        db = SessionLocal()
        try:
            return update_coin_metrics_service(db)
        finally:
            db.close()
