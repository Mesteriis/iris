from __future__ import annotations

import json

import pytest
from redis import Redis
from src.apps.cross_market.models import CoinRelation
from src.apps.market_data.domain import utc_now
from src.runtime.streams.publisher import flush_publisher

from tests.cross_market_support import (
    DEFAULT_START,
    create_cross_market_coin,
    create_pending_prediction,
    generate_close_series,
    run_prediction_evaluation,
    seed_candles,
)


@pytest.mark.asyncio
async def test_prediction_feedback_updates_relation_confidence_and_emits_event(
    async_db_session,
    db_session,
    redis_client: Redis,
    settings,
) -> None:
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
    relation = CoinRelation(
        leader_coin_id=int(leader.id),
        follower_coin_id=int(follower.id),
        correlation=0.82,
        lag_hours=4,
        confidence=0.65,
        updated_at=utc_now(),
    )
    db_session.add(relation)
    db_session.commit()
    closes = generate_close_series(
        start_price=48.0,
        returns=[0.0038, 0.0035, 0.003, 0.0028, 0.0025, 0.0022, 0.002, 0.0018, 0.0015, 0.0012] * 2,
    )
    seed_candles(db_session, coin=follower, interval="15m", closes=closes, start=DEFAULT_START)
    create_pending_prediction(
        db_session,
        leader_coin_id=int(leader.id),
        target_coin_id=int(follower.id),
        created_at=DEFAULT_START,
        lag_hours=4,
        expected_move="up",
    )

    await run_prediction_evaluation(async_db_session, emit_events=True)
    assert flush_publisher(timeout=5.0)

    db_session.refresh(relation)
    assert float(relation.confidence) > 0.65

    events = redis_client.xrange(settings.event_stream_name, "-", "+")
    prediction_events = [
        (fields["event_type"], json.loads(fields.get("payload") or "{}"))
        for _, fields in events
        if fields.get("event_type") in {"prediction_confirmed", "prediction_failed"}
    ]
    assert prediction_events
    event_type, payload = prediction_events[-1]
    assert event_type == "prediction_confirmed"
    assert int(payload["leader_coin_id"]) == int(leader.id)
    assert int(payload["target_coin_id"]) == int(follower.id)
