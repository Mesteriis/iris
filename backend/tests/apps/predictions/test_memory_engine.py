from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from src.apps.predictions.engine import _create_market_predictions_impl
from src.apps.cross_market.models import CoinRelation
from src.apps.predictions.models import MarketPrediction
from src.apps.predictions.cache import read_cached_prediction
from src.apps.market_data.domain import utc_now
from tests.cross_market_support import create_cross_market_coin


def test_prediction_memory_engine_creates_pending_predictions_and_cache(db_session) -> None:
    leader = create_cross_market_coin(
        db_session,
        symbol="BTCUSD_EVT",
        name="Bitcoin Event Test",
        sector_name="store_of_value",
    )
    follower = create_cross_market_coin(
        db_session,
        symbol="ETHUSD_EVT",
        name="Ethereum Event Test",
        sector_name="smart_contract",
    )
    db_session.add(
        CoinRelation(
            leader_coin_id=int(leader.id),
            follower_coin_id=int(follower.id),
            correlation=0.84,
            lag_hours=4,
            confidence=0.78,
            updated_at=utc_now() - timedelta(hours=1),
        )
    )
    db_session.commit()

    result = _create_market_predictions_impl(
        db_session,
        leader_coin_id=int(leader.id),
        prediction_event="leader_breakout",
        expected_move="up",
        base_confidence=0.8,
        emit_events=False,
    )

    prediction = db_session.scalar(
        select(MarketPrediction)
        .where(
            MarketPrediction.leader_coin_id == int(leader.id),
            MarketPrediction.target_coin_id == int(follower.id),
        )
        .limit(1)
    )
    assert result["status"] == "ok"
    assert result["created"] == 1
    assert prediction is not None
    assert prediction.status == "pending"
    assert prediction.lag_hours == 4
    cached = read_cached_prediction(int(prediction.id))
    assert cached is not None
    assert cached.status == "pending"
    assert cached.target_coin_id == int(follower.id)
