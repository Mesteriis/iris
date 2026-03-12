from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from src.apps.cross_market.models import CoinRelation
from src.apps.predictions.engine import (
    _apply_relation_feedback,
    _apply_relation_feedback_async,
    _evaluate_prediction_window,
    _evaluate_prediction_window_async,
    create_market_predictions,
    evaluate_pending_predictions,
    evaluate_pending_predictions_async,
)
from src.apps.predictions.models import MarketPrediction, PredictionResult
from tests.cross_market_support import (
    DEFAULT_START,
    create_cross_market_coin,
    create_pending_prediction,
    generate_close_series,
    seed_candles,
)


def test_prediction_creation_and_window_branches(db_session) -> None:
    leader = create_cross_market_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value")
    follower = create_cross_market_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract")
    disabled = create_cross_market_coin(db_session, symbol="SOLUSD_EVT", name="Solana Event Test", sector_name="smart_contract")
    disabled.enabled = False
    db_session.add_all(
        [
            CoinRelation(
                leader_coin_id=int(leader.id),
                follower_coin_id=int(follower.id),
                correlation=0.82,
                lag_hours=4,
                confidence=0.78,
                updated_at=DEFAULT_START,
            ),
            CoinRelation(
                leader_coin_id=int(leader.id),
                follower_coin_id=int(disabled.id),
                correlation=0.82,
                lag_hours=4,
                confidence=0.8,
                updated_at=DEFAULT_START,
            ),
        ]
    )
    db_session.commit()

    first = create_market_predictions(
        db_session,
        leader_coin_id=int(leader.id),
        prediction_event="leader_breakout",
        expected_move="up",
        base_confidence=0.8,
        emit_events=False,
    )
    second = create_market_predictions(
        db_session,
        leader_coin_id=int(leader.id),
        prediction_event="leader_breakout",
        expected_move="up",
        base_confidence=0.8,
        emit_events=False,
    )
    missing = create_market_predictions(
        db_session,
        leader_coin_id=999999,
        prediction_event="leader_breakout",
        expected_move="up",
        base_confidence=0.8,
        emit_events=False,
    )
    assert first["created"] == 1
    assert second["created"] == 0
    assert missing["reason"] == "relations_not_found"

    up_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(follower.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="up",
    )
    seed_candles(
        db_session,
        coin=follower,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.004] * 16),
        start=DEFAULT_START,
    )
    assert _evaluate_prediction_window(db_session, up_prediction, now=DEFAULT_START + timedelta(hours=4)) is not None

    too_short = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(disabled.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="down",
    )
    assert _evaluate_prediction_window(db_session, too_short, now=DEFAULT_START + timedelta(hours=1)) is None


def test_prediction_evaluation_handles_expired_existing_result_and_relation_feedback(db_session) -> None:
    leader = create_cross_market_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value")
    follower = create_cross_market_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract")
    db_session.add(
        CoinRelation(
            leader_coin_id=int(leader.id),
            follower_coin_id=int(follower.id),
            correlation=0.82,
            lag_hours=4,
            confidence=0.1,
            updated_at=DEFAULT_START,
        )
    )
    db_session.commit()
    seed_candles(
        db_session,
        coin=follower,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.0002] * 20),
        start=DEFAULT_START,
    )
    prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(follower.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="up",
    )
    db_session.add(
        PredictionResult(
            prediction_id=int(prediction.id),
            actual_move=0.0,
            success=False,
            profit=0.0,
            evaluated_at=DEFAULT_START,
        )
    )
    db_session.commit()

    result = evaluate_pending_predictions(db_session, emit_events=False)
    refreshed = db_session.get(MarketPrediction, int(prediction.id))
    outcome = db_session.scalar(select(PredictionResult).where(PredictionResult.prediction_id == int(prediction.id)).limit(1))
    relation = db_session.scalar(select(CoinRelation).where(CoinRelation.leader_coin_id == int(leader.id), CoinRelation.follower_coin_id == int(follower.id)).limit(1))

    assert result["expired"] == 1
    assert refreshed is not None and refreshed.status == "expired"
    assert outcome is not None and outcome.evaluated_at > DEFAULT_START
    assert relation is not None and 0.05 <= float(relation.confidence) <= 0.99
    assert _apply_relation_feedback(db_session, refreshed, success=True) is not None
    assert _apply_relation_feedback(db_session, MarketPrediction(leader_coin_id=1, target_coin_id=2, prediction_type="x", prediction_event="x", expected_move="up", lag_hours=1, confidence=0.1, evaluation_time=DEFAULT_START, status="pending"), success=True) is None


def test_prediction_sync_failure_expiry_and_pending_branches(db_session, monkeypatch) -> None:
    leader = create_cross_market_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value")
    failed_coin = create_cross_market_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract")
    expired_coin = create_cross_market_coin(db_session, symbol="SOLUSD_EVT", name="Solana Event Test", sector_name="smart_contract")
    pending_coin = create_cross_market_coin(db_session, symbol="ADAUSD_EVT", name="Cardano Event Test", sector_name="layer1")
    db_session.add_all(
        [
            CoinRelation(leader_coin_id=int(leader.id), follower_coin_id=int(failed_coin.id), correlation=0.8, lag_hours=4, confidence=0.75, updated_at=DEFAULT_START),
            CoinRelation(leader_coin_id=int(leader.id), follower_coin_id=int(expired_coin.id), correlation=0.8, lag_hours=4, confidence=0.75, updated_at=DEFAULT_START),
        ]
    )
    db_session.commit()

    seed_candles(
        db_session,
        coin=failed_coin,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.004] * 20),
        start=DEFAULT_START,
    )
    seed_candles(
        db_session,
        coin=expired_coin,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.0003] * 20),
        start=DEFAULT_START,
    )
    seed_candles(
        db_session,
        coin=pending_coin,
        interval="15m",
        closes=[50.0],
        start=DEFAULT_START,
    )

    failed_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(failed_coin.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="down",
    )
    expired_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(expired_coin.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="down",
    )
    pending_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(pending_coin.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="up",
    )
    assert _evaluate_prediction_window(db_session, failed_prediction, now=DEFAULT_START + timedelta(hours=4)) is not None

    published: list[str] = []
    monkeypatch.setattr("src.apps.predictions.engine.publish_event", lambda event_type, payload: published.append(event_type))
    result = evaluate_pending_predictions(db_session, emit_events=True)
    db_session.expire_all()

    assert result["failed"] == 1
    assert result["expired"] == 1
    assert db_session.get(MarketPrediction, int(failed_prediction.id)).status == "failed"
    assert db_session.get(MarketPrediction, int(expired_prediction.id)).status == "expired"
    assert db_session.get(MarketPrediction, int(pending_prediction.id)).status == "pending"
    assert published.count("prediction_failed") == 2


def test_prediction_window_direct_confirmed_and_pending_paths(db_session) -> None:
    leader = create_cross_market_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value")
    confirmed_coin = create_cross_market_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract")
    pending_coin = create_cross_market_coin(db_session, symbol="SOLUSD_EVT", name="Solana Event Test", sector_name="smart_contract")

    seed_candles(
        db_session,
        coin=confirmed_coin,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[-0.004] * 20),
        start=DEFAULT_START,
    )
    seed_candles(
        db_session,
        coin=pending_coin,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.0003] * 4),
        start=DEFAULT_START,
    )

    confirmed_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(confirmed_coin.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="down",
    )
    pending_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(pending_coin.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="down",
    )

    assert _evaluate_prediction_window(
        db_session,
        confirmed_prediction,
        now=DEFAULT_START + timedelta(hours=4),
    ).status == "confirmed"
    assert _evaluate_prediction_window(
        db_session,
        pending_prediction,
        now=DEFAULT_START + timedelta(hours=1),
    ) is None

    up_pending_coin = create_cross_market_coin(db_session, symbol="UPPEND_EVT", name="Up Pending Test", sector_name="smart_contract")
    seed_candles(
        db_session,
        coin=up_pending_coin,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.0003] * 4),
        start=DEFAULT_START,
    )
    up_pending_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(up_pending_coin.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="up",
    )
    assert _evaluate_prediction_window(
        db_session,
        up_pending_prediction,
        now=DEFAULT_START + timedelta(hours=1),
    ) is None


@pytest.mark.asyncio
async def test_prediction_async_engine_covers_bearish_paths(async_db_session, db_session) -> None:
    leader = create_cross_market_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value")
    follower = create_cross_market_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract")
    db_session.add(
        CoinRelation(
            leader_coin_id=int(leader.id),
            follower_coin_id=int(follower.id),
            correlation=0.82,
            lag_hours=4,
            confidence=0.7,
            updated_at=DEFAULT_START,
        )
    )
    db_session.commit()
    seed_candles(
        db_session,
        coin=follower,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[-0.004] * 20),
        start=DEFAULT_START,
    )
    prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(follower.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="down",
    )

    async_prediction = await async_db_session.get(MarketPrediction, int(prediction.id))
    assert async_prediction is not None
    outcome = await _evaluate_prediction_window_async(async_db_session, async_prediction, now=DEFAULT_START + timedelta(hours=4))
    assert outcome is not None
    assert outcome.status == "confirmed"

    result = await evaluate_pending_predictions_async(async_db_session, emit_events=False)
    db_session.expire_all()
    refreshed = db_session.get(MarketPrediction, int(prediction.id))
    assert result["confirmed"] == 1
    assert refreshed is not None and refreshed.status == "confirmed"


@pytest.mark.asyncio
async def test_prediction_async_failure_expiry_update_and_pending_branches(async_db_session, db_session, monkeypatch) -> None:
    leader = create_cross_market_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value")
    up_failed_coin = create_cross_market_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract")
    up_expired_coin = create_cross_market_coin(db_session, symbol="SOLUSD_EVT", name="Solana Event Test", sector_name="smart_contract")
    down_failed_coin = create_cross_market_coin(db_session, symbol="ADAUSD_EVT", name="Cardano Event Test", sector_name="layer1")
    down_expired_coin = create_cross_market_coin(db_session, symbol="XRPUSD_EVT", name="Ripple Event Test", sector_name="payments")
    pending_coin = create_cross_market_coin(db_session, symbol="DOGEUSD_EVT", name="Dogecoin Event Test", sector_name="payments")
    db_session.add_all(
        [
            CoinRelation(leader_coin_id=int(leader.id), follower_coin_id=int(up_failed_coin.id), correlation=0.8, lag_hours=4, confidence=0.75, updated_at=DEFAULT_START),
            CoinRelation(leader_coin_id=int(leader.id), follower_coin_id=int(up_expired_coin.id), correlation=0.8, lag_hours=4, confidence=0.75, updated_at=DEFAULT_START),
            CoinRelation(leader_coin_id=int(leader.id), follower_coin_id=int(down_failed_coin.id), correlation=0.8, lag_hours=4, confidence=0.75, updated_at=DEFAULT_START),
            CoinRelation(leader_coin_id=int(leader.id), follower_coin_id=int(down_expired_coin.id), correlation=0.8, lag_hours=4, confidence=0.75, updated_at=DEFAULT_START),
        ]
    )
    db_session.commit()

    seed_candles(
        db_session,
        coin=up_failed_coin,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[-0.004] * 20),
        start=DEFAULT_START,
    )
    seed_candles(
        db_session,
        coin=up_expired_coin,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.0003] * 20),
        start=DEFAULT_START,
    )
    seed_candles(
        db_session,
        coin=down_failed_coin,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.004] * 20),
        start=DEFAULT_START,
    )
    seed_candles(
        db_session,
        coin=down_expired_coin,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.0003] * 20),
        start=DEFAULT_START,
    )
    seed_candles(
        db_session,
        coin=pending_coin,
        interval="15m",
        closes=[50.0],
        start=DEFAULT_START,
    )

    up_failed_prediction = create_pending_prediction(db_session, leader_coin_id=int(leader.id), target_coin_id=int(up_failed_coin.id), created_at=DEFAULT_START, lag_hours=4, expected_move="up")
    up_expired_prediction = create_pending_prediction(db_session, leader_coin_id=int(leader.id), target_coin_id=int(up_expired_coin.id), created_at=DEFAULT_START, lag_hours=4, expected_move="up")
    down_failed_prediction = create_pending_prediction(db_session, leader_coin_id=int(leader.id), target_coin_id=int(down_failed_coin.id), created_at=DEFAULT_START, lag_hours=4, expected_move="down")
    down_expired_prediction = create_pending_prediction(db_session, leader_coin_id=int(leader.id), target_coin_id=int(down_expired_coin.id), created_at=DEFAULT_START, lag_hours=4, expected_move="down")
    pending_prediction = create_pending_prediction(db_session, leader_coin_id=int(leader.id), target_coin_id=int(pending_coin.id), created_at=DEFAULT_START, lag_hours=4, expected_move="down")
    db_session.add(
        PredictionResult(
            prediction_id=int(down_expired_prediction.id),
            actual_move=0.0,
            success=False,
            profit=0.0,
            evaluated_at=DEFAULT_START,
        )
    )
    db_session.commit()

    published: list[str] = []
    monkeypatch.setattr("src.apps.predictions.engine.publish_event", lambda event_type, payload: published.append(event_type))
    async def _noop_cache_prediction_snapshot_async(**kwargs):
        return None

    monkeypatch.setattr(
        "src.apps.predictions.engine.cache_prediction_snapshot_async",
        _noop_cache_prediction_snapshot_async,
    )

    async_up_failed = await async_db_session.get(MarketPrediction, int(up_failed_prediction.id))
    async_down_expired = await async_db_session.get(MarketPrediction, int(down_expired_prediction.id))
    assert async_up_failed is not None and async_down_expired is not None
    assert (await _evaluate_prediction_window_async(async_db_session, async_up_failed, now=DEFAULT_START + timedelta(hours=4))).status == "failed"
    assert (await _evaluate_prediction_window_async(async_db_session, async_down_expired, now=DEFAULT_START + timedelta(hours=4))).status == "expired"

    result = await evaluate_pending_predictions_async(async_db_session, emit_events=True)
    db_session.expire_all()

    assert result["failed"] == 2
    assert result["expired"] == 2
    assert db_session.get(MarketPrediction, int(up_failed_prediction.id)).status == "failed"
    assert db_session.get(MarketPrediction, int(up_expired_prediction.id)).status == "expired"
    assert db_session.get(MarketPrediction, int(down_failed_prediction.id)).status == "failed"
    assert db_session.get(MarketPrediction, int(down_expired_prediction.id)).status == "expired"
    assert db_session.get(MarketPrediction, int(pending_prediction.id)).status == "pending"
    updated_result = db_session.scalar(select(PredictionResult).where(PredictionResult.prediction_id == int(down_expired_prediction.id)).limit(1))
    assert updated_result is not None
    assert updated_result.evaluated_at > DEFAULT_START
    assert published.count("prediction_failed") == 4
    assert await _apply_relation_feedback_async(
        async_db_session,
        MarketPrediction(
            leader_coin_id=999,
            target_coin_id=998,
            prediction_type="cross_market_follow_through",
            prediction_event="leader_breakout",
            expected_move="up",
            lag_hours=1,
            confidence=0.5,
            evaluation_time=DEFAULT_START,
            status="pending",
        ),
        success=True,
    ) is None


@pytest.mark.asyncio
async def test_prediction_async_direct_confirmed_and_pending_paths(async_db_session, db_session) -> None:
    leader = create_cross_market_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value")
    confirmed_coin = create_cross_market_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract")
    pending_coin = create_cross_market_coin(db_session, symbol="SOLUSD_EVT", name="Solana Event Test", sector_name="smart_contract")

    seed_candles(
        db_session,
        coin=confirmed_coin,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.004] * 20),
        start=DEFAULT_START,
    )
    seed_candles(
        db_session,
        coin=pending_coin,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.0003] * 4),
        start=DEFAULT_START,
    )

    confirmed_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(confirmed_coin.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="up",
    )
    pending_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(pending_coin.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="down",
    )

    async_confirmed = await async_db_session.get(MarketPrediction, int(confirmed_prediction.id))
    async_pending = await async_db_session.get(MarketPrediction, int(pending_prediction.id))
    assert async_confirmed is not None and async_pending is not None
    assert (
        await _evaluate_prediction_window_async(
            async_db_session,
            async_confirmed,
            now=DEFAULT_START + timedelta(hours=4),
        )
    ).status == "confirmed"
    assert await _evaluate_prediction_window_async(
        async_db_session,
        async_pending,
        now=DEFAULT_START + timedelta(hours=1),
    ) is None

    up_pending_coin = create_cross_market_coin(db_session, symbol="UPPEND_EVT", name="Up Pending Test", sector_name="smart_contract")
    seed_candles(
        db_session,
        coin=up_pending_coin,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.0003] * 4),
        start=DEFAULT_START,
    )
    up_pending_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(up_pending_coin.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="up",
    )
    async_up_pending = await async_db_session.get(MarketPrediction, int(up_pending_prediction.id))
    assert async_up_pending is not None
    assert await _evaluate_prediction_window_async(
        async_db_session,
        async_up_pending,
        now=DEFAULT_START + timedelta(hours=1),
    ) is None
