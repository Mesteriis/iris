from __future__ import annotations

from datetime import datetime

from app.db.session import SessionLocal
from app.services.analytics_events import NewCandleEvent
from app.services.analytics_service import handle_new_candle_event as handle_new_candle_event_service
from app.services.analytics_service import list_pending_new_candle_events
from app.taskiq.broker import broker
from app.taskiq.locks import redis_task_lock

NEW_CANDLE_EVENT_LOCK_TIMEOUT_SECONDS = 300


def get_pending_new_candle_events() -> list[NewCandleEvent]:
    db = SessionLocal()
    try:
        return list(list_pending_new_candle_events(db))
    finally:
        db.close()


@broker.task
def handle_new_candle_event(coin_id: int, timeframe: int, timestamp: str) -> dict[str, object]:
    event = NewCandleEvent(
        coin_id=int(coin_id),
        timeframe=int(timeframe),
        timestamp=datetime.fromisoformat(timestamp),
    )
    with redis_task_lock(
        f"iris:tasklock:new_candle_event:{event.coin_id}:{event.timeframe}",
        timeout=NEW_CANDLE_EVENT_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {
                "status": "skipped",
                "reason": "new_candle_event_in_progress",
                "coin_id": event.coin_id,
                "timeframe": event.timeframe,
            }

        db = SessionLocal()
        try:
            return handle_new_candle_event_service(db, event)
        finally:
            db.close()
