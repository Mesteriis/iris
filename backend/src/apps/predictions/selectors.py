from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from src.apps.market_data.models import Coin
from src.apps.predictions.models import MarketPrediction
from src.apps.predictions.models import PredictionResult


def list_predictions(
    db: Session,
    *,
    limit: int = 100,
    status: str | None = None,
) -> Sequence[dict[str, Any]]:
    leader_coin = aliased(Coin)
    target_coin = aliased(Coin)
    stmt = (
        select(
            MarketPrediction.id,
            MarketPrediction.prediction_type,
            MarketPrediction.leader_coin_id,
            leader_coin.symbol.label("leader_symbol"),
            MarketPrediction.target_coin_id,
            target_coin.symbol.label("target_symbol"),
            MarketPrediction.prediction_event,
            MarketPrediction.expected_move,
            MarketPrediction.lag_hours,
            MarketPrediction.confidence,
            MarketPrediction.created_at,
            MarketPrediction.evaluation_time,
            MarketPrediction.status,
            PredictionResult.actual_move,
            PredictionResult.success,
            PredictionResult.profit,
            PredictionResult.evaluated_at,
        )
        .join(leader_coin, leader_coin.id == MarketPrediction.leader_coin_id)
        .join(target_coin, target_coin.id == MarketPrediction.target_coin_id)
        .outerjoin(PredictionResult, PredictionResult.prediction_id == MarketPrediction.id)
        .order_by(MarketPrediction.created_at.desc(), MarketPrediction.id.desc())
        .limit(max(limit, 1))
    )
    if status is not None:
        stmt = stmt.where(MarketPrediction.status == status)
    rows = db.execute(stmt).all()
    return [dict(row._mapping) for row in rows]
