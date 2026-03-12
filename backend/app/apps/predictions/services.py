from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.apps.market_data.models import Coin
from app.apps.predictions.cache import (
    cache_prediction_snapshot,
    cache_prediction_snapshot_async,
    read_cached_prediction,
    read_cached_prediction_async,
)
from app.apps.predictions.engine import (
    create_market_predictions,
    evaluate_pending_predictions,
    evaluate_pending_predictions_async,
)
from app.apps.predictions.models import MarketPrediction, PredictionResult
from app.apps.predictions.selectors import list_predictions


async def list_predictions_async(
    db: AsyncSession,
    *,
    limit: int = 100,
    status: str | None = None,
):
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
    rows = (await db.execute(stmt)).all()
    return [dict(row._mapping) for row in rows]


__all__ = [
    "cache_prediction_snapshot",
    "cache_prediction_snapshot_async",
    "create_market_predictions",
    "evaluate_pending_predictions",
    "evaluate_pending_predictions_async",
    "list_predictions",
    "list_predictions_async",
    "read_cached_prediction",
    "read_cached_prediction_async",
]
