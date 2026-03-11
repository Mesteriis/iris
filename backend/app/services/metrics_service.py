from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy.orm import Session

from app.services.analytics_service import (
    delete_coin_metrics_row,
    ensure_coin_metrics_row,
    list_coin_metrics,
)


def mark_coin_metrics_dirty(coin_id: int) -> None:
    del coin_id


def clear_coin_metrics_dirty(*coin_ids: int) -> None:
    del coin_ids


def calculate_coin_metrics(db: Session, coin: object) -> dict[str, Any]:
    del db, coin
    raise RuntimeError("Legacy metrics_service is disabled. Use the analytics pipeline instead.")


def list_coin_ids_requiring_metrics_update(db: Session) -> list[int]:
    del db
    return []


def update_coin_metrics(
    db: Session,
    coin_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    del db, coin_ids
    return {
        "status": "skipped",
        "reason": "metrics_are_updated_by_new_candle_event_pipeline",
        "coins": 0,
        "updated": 0,
    }


__all__ = [
    "calculate_coin_metrics",
    "clear_coin_metrics_dirty",
    "delete_coin_metrics_row",
    "ensure_coin_metrics_row",
    "list_coin_ids_requiring_metrics_update",
    "list_coin_metrics",
    "mark_coin_metrics_dirty",
    "update_coin_metrics",
]
