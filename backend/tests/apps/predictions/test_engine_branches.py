from datetime import timedelta

import pytest
from sqlalchemy import select
from src.apps.cross_market.models import CoinRelation
from src.apps.predictions.models import MarketPrediction, PredictionResult
from src.apps.predictions.services import PredictionService, PredictionSideEffectDispatcher
from src.core.db.uow import SessionUnitOfWork

from tests.cross_market_support import (
    DEFAULT_START,
    create_cross_market_coin,
    create_pending_prediction,
    generate_close_series,
    run_prediction_creation,
    run_prediction_evaluation,
    seed_candles,
)


async def _evaluate_prediction_window(
    async_db_session,
    prediction_id: int,
    *,
    now,
):
    async with SessionUnitOfWork(async_db_session) as uow:
        service = PredictionService(uow)
        prediction = await uow.session.get(MarketPrediction, int(prediction_id))
        assert prediction is not None
        return await service._evaluate_prediction_window(prediction, now=now)


async def _apply_relation_feedback(
    async_db_session,
    prediction_id: int,
    *,
    success: bool,
):
    async with SessionUnitOfWork(async_db_session) as uow:
        service = PredictionService(uow)
        prediction = await uow.session.get(MarketPrediction, int(prediction_id))
        assert prediction is not None
        relation = await service._apply_relation_feedback(prediction, success=success)
        if relation is not None:
            await uow.commit()
        return relation


@pytest.mark.asyncio
async def test_prediction_creation_and_window_branches(async_db_session, db_session) -> None:
    leader = create_cross_market_coin(
        db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value"
    )
    follower = create_cross_market_coin(
        db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract"
    )
    disabled = create_cross_market_coin(
        db_session, symbol="SOLUSD_EVT", name="Solana Event Test", sector_name="smart_contract"
    )
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

    first = await run_prediction_creation(
        async_db_session,
        leader_coin_id=int(leader.id),
        prediction_event="leader_breakout",
        expected_move="up",
        base_confidence=0.8,
        emit_events=False,
    )
    second = await run_prediction_creation(
        async_db_session,
        leader_coin_id=int(leader.id),
        prediction_event="leader_breakout",
        expected_move="up",
        base_confidence=0.8,
        emit_events=False,
    )
    missing = await run_prediction_creation(
        async_db_session,
        leader_coin_id=999999,
        prediction_event="leader_breakout",
        expected_move="up",
        base_confidence=0.8,
        emit_events=False,
    )
    assert first.created == 1
    assert second.created == 0
    assert missing.reason == "relations_not_found"

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
    assert (
        await _evaluate_prediction_window(
            async_db_session,
            int(up_prediction.id),
            now=DEFAULT_START + timedelta(hours=4),
        )
        is not None
    )

    too_short = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(disabled.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="down",
    )
    assert (
        await _evaluate_prediction_window(
            async_db_session,
            int(too_short.id),
            now=DEFAULT_START + timedelta(hours=1),
        )
        is None
    )


@pytest.mark.asyncio
async def test_prediction_creation_defers_cache_until_after_commit(async_db_session, db_session, monkeypatch) -> None:
    leader = create_cross_market_coin(
        db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value"
    )
    follower = create_cross_market_coin(
        db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract"
    )
    db_session.add(
        CoinRelation(
            leader_coin_id=int(leader.id),
            follower_coin_id=int(follower.id),
            correlation=0.82,
            lag_hours=4,
            confidence=0.78,
            updated_at=DEFAULT_START,
        )
    )
    db_session.commit()

    events: list[str] = []
    original_commit = async_db_session.commit

    async def _commit() -> None:
        events.append("commit")
        await original_commit()

    async def _cache_prediction_snapshot_async(**_kwargs) -> None:
        events.append("cache")

    monkeypatch.setattr(async_db_session, "commit", _commit)
    monkeypatch.setattr(
        "src.apps.predictions.services.cache_prediction_snapshot_async",
        _cache_prediction_snapshot_async,
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await PredictionService(uow).create_market_predictions(
            leader_coin_id=int(leader.id),
            prediction_event="leader_breakout",
            expected_move="up",
            base_confidence=0.8,
            emit_events=False,
        )
        await uow.commit()
    await PredictionSideEffectDispatcher().apply_creation(result)

    assert result.created == 1
    assert events == ["commit", "cache"]


@pytest.mark.asyncio
async def test_prediction_evaluation_handles_expired_existing_result_and_relation_feedback(
    async_db_session,
    db_session,
) -> None:
    leader = create_cross_market_coin(
        db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value"
    )
    follower = create_cross_market_coin(
        db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract"
    )
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

    result = await run_prediction_evaluation(async_db_session, emit_events=False)
    db_session.expire_all()
    refreshed = db_session.get(MarketPrediction, int(prediction.id))
    outcome = db_session.scalar(
        select(PredictionResult).where(PredictionResult.prediction_id == int(prediction.id)).limit(1)
    )
    relation = db_session.scalar(
        select(CoinRelation)
        .where(
            CoinRelation.leader_coin_id == int(leader.id),
            CoinRelation.follower_coin_id == int(follower.id),
        )
        .limit(1)
    )

    assert result.expired == 1
    assert refreshed is not None and refreshed.status == "expired"
    assert outcome is not None and outcome.evaluated_at > DEFAULT_START
    assert relation is not None and 0.05 <= float(relation.confidence) <= 0.99
    assert await _apply_relation_feedback(async_db_session, int(prediction.id), success=True) is not None

    async with SessionUnitOfWork(async_db_session) as uow:
        missing_relation = await PredictionService(uow)._apply_relation_feedback(
            MarketPrediction(
                leader_coin_id=1,
                target_coin_id=2,
                prediction_type="x",
                prediction_event="x",
                expected_move="up",
                lag_hours=1,
                confidence=0.1,
                evaluation_time=DEFAULT_START,
                status="pending",
            ),
            success=True,
        )
    assert missing_relation is None


@pytest.mark.asyncio
async def test_prediction_evaluation_failure_expiry_update_and_pending_branches(
    async_db_session,
    db_session,
    monkeypatch,
) -> None:
    leader = create_cross_market_coin(
        db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value"
    )
    up_failed_coin = create_cross_market_coin(
        db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract"
    )
    up_expired_coin = create_cross_market_coin(
        db_session, symbol="SOLUSD_EVT", name="Solana Event Test", sector_name="smart_contract"
    )
    down_failed_coin = create_cross_market_coin(
        db_session, symbol="ADAUSD_EVT", name="Cardano Event Test", sector_name="layer1"
    )
    down_expired_coin = create_cross_market_coin(
        db_session, symbol="XRPUSD_EVT", name="Ripple Event Test", sector_name="payments"
    )
    pending_coin = create_cross_market_coin(
        db_session, symbol="DOGEUSD_EVT", name="Dogecoin Event Test", sector_name="payments"
    )
    db_session.add_all(
        [
            CoinRelation(
                leader_coin_id=int(leader.id),
                follower_coin_id=int(up_failed_coin.id),
                correlation=0.8,
                lag_hours=4,
                confidence=0.75,
                updated_at=DEFAULT_START,
            ),
            CoinRelation(
                leader_coin_id=int(leader.id),
                follower_coin_id=int(up_expired_coin.id),
                correlation=0.8,
                lag_hours=4,
                confidence=0.75,
                updated_at=DEFAULT_START,
            ),
            CoinRelation(
                leader_coin_id=int(leader.id),
                follower_coin_id=int(down_failed_coin.id),
                correlation=0.8,
                lag_hours=4,
                confidence=0.75,
                updated_at=DEFAULT_START,
            ),
            CoinRelation(
                leader_coin_id=int(leader.id),
                follower_coin_id=int(down_expired_coin.id),
                correlation=0.8,
                lag_hours=4,
                confidence=0.75,
                updated_at=DEFAULT_START,
            ),
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

    up_failed_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(up_failed_coin.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="up",
    )
    up_expired_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(up_expired_coin.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="up",
    )
    down_failed_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(down_failed_coin.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="down",
    )
    down_expired_prediction = create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(down_expired_coin.id),
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

    async def _noop_cache_prediction_snapshot_async(**_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "src.apps.predictions.services.publish_event", lambda event_type, payload: published.append(event_type)
    )
    monkeypatch.setattr(
        "src.apps.predictions.services.cache_prediction_snapshot_async",
        _noop_cache_prediction_snapshot_async,
    )

    assert (
        await _evaluate_prediction_window(
            async_db_session,
            int(up_failed_prediction.id),
            now=DEFAULT_START + timedelta(hours=4),
        )
    ).status == "failed"
    assert (
        await _evaluate_prediction_window(
            async_db_session,
            int(down_expired_prediction.id),
            now=DEFAULT_START + timedelta(hours=4),
        )
    ).status == "expired"

    result = await run_prediction_evaluation(async_db_session, emit_events=True)
    db_session.expire_all()

    assert result.failed == 2
    assert result.expired == 2
    assert db_session.get(MarketPrediction, int(up_failed_prediction.id)).status == "failed"
    assert db_session.get(MarketPrediction, int(up_expired_prediction.id)).status == "expired"
    assert db_session.get(MarketPrediction, int(down_failed_prediction.id)).status == "failed"
    assert db_session.get(MarketPrediction, int(down_expired_prediction.id)).status == "expired"
    assert db_session.get(MarketPrediction, int(pending_prediction.id)).status == "pending"
    updated_result = db_session.scalar(
        select(PredictionResult).where(PredictionResult.prediction_id == int(down_expired_prediction.id)).limit(1)
    )
    assert updated_result is not None
    assert updated_result.evaluated_at > DEFAULT_START
    assert published.count("prediction_failed") == 4

    async with SessionUnitOfWork(async_db_session) as uow:
        missing_relation = await PredictionService(uow)._apply_relation_feedback(
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
        )
    assert missing_relation is None


@pytest.mark.asyncio
async def test_prediction_evaluation_defers_cache_and_events_until_after_commit(
    async_db_session,
    db_session,
    monkeypatch,
) -> None:
    leader = create_cross_market_coin(
        db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value"
    )
    follower = create_cross_market_coin(
        db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract"
    )
    db_session.add(
        CoinRelation(
            leader_coin_id=int(leader.id),
            follower_coin_id=int(follower.id),
            correlation=0.82,
            lag_hours=4,
            confidence=0.78,
            updated_at=DEFAULT_START,
        )
    )
    db_session.commit()
    seed_candles(
        db_session,
        coin=follower,
        interval="15m",
        closes=generate_close_series(start_price=50.0, returns=[0.004] * 20),
        start=DEFAULT_START,
    )
    create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(follower.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="up",
    )

    events: list[str] = []
    original_commit = async_db_session.commit

    async def _commit() -> None:
        events.append("commit")
        await original_commit()

    async def _cache_prediction_snapshot_async(**_kwargs) -> None:
        events.append("cache")

    monkeypatch.setattr(async_db_session, "commit", _commit)
    monkeypatch.setattr(
        "src.apps.predictions.services.cache_prediction_snapshot_async",
        _cache_prediction_snapshot_async,
    )
    monkeypatch.setattr(
        "src.apps.predictions.services.publish_event", lambda *_args, **_kwargs: events.append("publish")
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await PredictionService(uow).evaluate_pending_predictions(emit_events=True)
        await uow.commit()
    await PredictionSideEffectDispatcher().apply_evaluation(result)

    assert result.confirmed == 1
    assert events == ["commit", "cache", "publish"]


@pytest.mark.asyncio
async def test_prediction_window_direct_confirmed_and_pending_paths(async_db_session, db_session) -> None:
    leader = create_cross_market_coin(
        db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value"
    )
    confirmed_coin = create_cross_market_coin(
        db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract"
    )
    pending_coin = create_cross_market_coin(
        db_session, symbol="SOLUSD_EVT", name="Solana Event Test", sector_name="smart_contract"
    )

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

    assert (
        await _evaluate_prediction_window(
            async_db_session,
            int(confirmed_prediction.id),
            now=DEFAULT_START + timedelta(hours=4),
        )
    ).status == "confirmed"
    assert (
        await _evaluate_prediction_window(
            async_db_session,
            int(pending_prediction.id),
            now=DEFAULT_START + timedelta(hours=1),
        )
        is None
    )

    up_pending_coin = create_cross_market_coin(
        db_session, symbol="UPPEND_EVT", name="Up Pending Test", sector_name="smart_contract"
    )
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
    assert (
        await _evaluate_prediction_window(
            async_db_session,
            int(up_pending_prediction.id),
            now=DEFAULT_START + timedelta(hours=1),
        )
        is None
    )


@pytest.mark.asyncio
async def test_prediction_service_covers_bearish_paths(async_db_session, db_session) -> None:
    leader = create_cross_market_coin(
        db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test", sector_name="store_of_value"
    )
    follower = create_cross_market_coin(
        db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test", sector_name="smart_contract"
    )
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

    outcome = await _evaluate_prediction_window(
        async_db_session,
        int(prediction.id),
        now=DEFAULT_START + timedelta(hours=4),
    )
    assert outcome is not None
    assert outcome.status == "confirmed"

    result = await run_prediction_evaluation(async_db_session, emit_events=False)
    db_session.expire_all()
    refreshed = db_session.get(MarketPrediction, int(prediction.id))
    assert result.confirmed == 1
    assert refreshed is not None and refreshed.status == "confirmed"
