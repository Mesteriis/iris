from __future__ import annotations

from sqlalchemy import select

from app.analysis.prediction_memory_engine import evaluate_pending_predictions
from app.models.market_prediction import MarketPrediction
from app.models.prediction_result import PredictionResult
from tests.cross_market_support import (
    DEFAULT_START,
    create_cross_market_coin,
    create_pending_prediction,
    generate_close_series,
    seed_candles,
)


def test_prediction_evaluation_marks_prediction_confirmed(db_session) -> None:
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
    closes = generate_close_series(
        start_price=50.0,
        returns=[0.0035, 0.004, 0.0025, 0.003, 0.002, 0.0025, 0.0018, 0.0015, 0.0012, 0.001] * 2,
    )
    seed_candles(db_session, coin=follower, interval="15m", closes=closes, start=DEFAULT_START)
    prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(follower.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="up",
    )

    result = evaluate_pending_predictions(db_session, emit_events=False)

    refreshed = db_session.get(MarketPrediction, int(prediction.id))
    outcome = db_session.scalar(
        select(PredictionResult).where(PredictionResult.prediction_id == int(prediction.id)).limit(1)
    )
    assert result["status"] == "ok"
    assert result["confirmed"] >= 1
    assert refreshed is not None
    assert refreshed.status == "confirmed"
    assert outcome is not None
    assert outcome.success is True
    assert float(outcome.profit) > 0


def test_prediction_evaluation_marks_prediction_failed(db_session) -> None:
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
    closes = generate_close_series(
        start_price=50.0,
        returns=[-0.004, -0.0035, -0.0028, -0.003, -0.0022, -0.002, -0.0018, -0.0015, -0.0012, -0.001] * 2,
    )
    seed_candles(db_session, coin=follower, interval="15m", closes=closes, start=DEFAULT_START)
    prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(follower.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="up",
    )

    result = evaluate_pending_predictions(db_session, emit_events=False)

    refreshed = db_session.get(MarketPrediction, int(prediction.id))
    outcome = db_session.scalar(
        select(PredictionResult).where(PredictionResult.prediction_id == int(prediction.id)).limit(1)
    )
    assert result["status"] == "ok"
    assert result["failed"] >= 1
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert outcome is not None
    assert outcome.success is False
    assert float(outcome.profit) < 0
