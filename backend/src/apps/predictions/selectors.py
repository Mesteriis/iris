from __future__ import annotations

import logging
from typing import Any, Sequence

from sqlalchemy.orm import Session

from src.apps.predictions.models import MarketPrediction
from src.apps.predictions.query_builders import prediction_select as _prediction_select
from src.apps.predictions.read_models import PredictionReadModel, prediction_read_model_from_mapping
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value


def _prediction_payload(item: PredictionReadModel) -> dict[str, Any]:
    return {
        "id": int(item.id),
        "prediction_type": str(item.prediction_type),
        "leader_coin_id": int(item.leader_coin_id),
        "leader_symbol": str(item.leader_symbol),
        "target_coin_id": int(item.target_coin_id),
        "target_symbol": str(item.target_symbol),
        "prediction_event": str(item.prediction_event),
        "expected_move": str(item.expected_move),
        "lag_hours": int(item.lag_hours),
        "confidence": float(item.confidence),
        "created_at": item.created_at,
        "evaluation_time": item.evaluation_time,
        "status": str(item.status),
        "actual_move": float(item.actual_move) if item.actual_move is not None else None,
        "success": bool(item.success) if item.success is not None else None,
        "profit": float(item.profit) if item.profit is not None else None,
        "evaluated_at": item.evaluated_at,
    }


class PredictionCompatibilityQuery:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _log(self, level: int, event: str, /, **fields: Any) -> None:
        PERSISTENCE_LOGGER.log(
            level,
            event,
            extra={
                "persistence": {
                    "event": event,
                    "component_type": "compatibility_query",
                    "domain": "predictions",
                    "component": "PredictionCompatibilityQuery",
                    **{key: sanitize_log_value(value) for key, value in fields.items()},
                }
            },
        )

    def list_predictions(
        self,
        *,
        limit: int = 100,
        status: str | None = None,
    ) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_predictions.deprecated",
            mode="read",
            limit=limit,
            status=status,
        )
        stmt = _prediction_select().order_by(MarketPrediction.created_at.desc(), MarketPrediction.id.desc()).limit(
            max(limit, 1)
        )
        if status is not None:
            stmt = stmt.where(MarketPrediction.status == status)
        rows = self._db.execute(stmt).all()
        return [_prediction_payload(prediction_read_model_from_mapping(row._mapping)) for row in rows]


def list_predictions(
    db: Session,
    *,
    limit: int = 100,
    status: str | None = None,
) -> Sequence[dict[str, Any]]:
    return PredictionCompatibilityQuery(db).list_predictions(
        limit=limit,
        status=status,
    )


__all__ = ["PredictionCompatibilityQuery", "list_predictions"]
