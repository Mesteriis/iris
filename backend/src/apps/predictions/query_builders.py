from sqlalchemy import select
from sqlalchemy.orm import aliased

from src.apps.market_data.models import Coin
from src.apps.predictions.models import MarketPrediction, PredictionResult


def prediction_select():
    leader_coin = aliased(Coin)
    target_coin = aliased(Coin)
    return (
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
    )


__all__ = ["prediction_select"]
