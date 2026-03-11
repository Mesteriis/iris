from __future__ import annotations

from app.db.session import SessionLocal
from app.portfolio.engine import sync_exchange_balances
from app.taskiq.broker import broker
from app.taskiq.locks import redis_task_lock

PORTFOLIO_SYNC_LOCK_TIMEOUT_SECONDS = 240


@broker.task
def portfolio_sync_job() -> dict[str, object]:
    with redis_task_lock("iris:tasklock:portfolio_sync", timeout=PORTFOLIO_SYNC_LOCK_TIMEOUT_SECONDS) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "portfolio_sync_in_progress"}
        db = SessionLocal()
        try:
            return sync_exchange_balances(db, emit_events=True)
        finally:
            db.close()
