from __future__ import annotations

import json
import multiprocessing

import pytest
from redis import Redis
from sqlalchemy import select
from src.apps.hypothesis_engine.models import AIHypothesis, AIWeight
from src.apps.hypothesis_engine.query_services import HypothesisQueryService
from src.apps.hypothesis_engine.tasks.hypothesis_tasks import evaluate_hypotheses_job
from src.apps.market_data.domain import utc_now
from src.apps.market_data.models import Candle
from src.runtime.control_plane.worker import create_topology_dispatcher_consumer
from src.runtime.streams.publisher import flush_publisher, publish_event
from src.runtime.streams.runner import run_worker_loop


def _run_dispatcher_loop() -> None:
    consumer = create_topology_dispatcher_consumer()
    try:
        consumer.run()
    finally:
        consumer.close()


@pytest.mark.asyncio
async def test_signal_created_pipeline_persists_and_publishes_hypothesis(
    async_db_session,
    seeded_market,
    settings,
    wait_until,
    monkeypatch,
) -> None:
    coin_id = int(seeded_market["ETHUSD_EVT"]["coin_id"])
    event_timestamp = seeded_market["ETHUSD_EVT"]["latest_timestamp"]
    monkeypatch.setenv(
        "IRIS_AI_PROVIDERS",
        json.dumps(
            [
                {
                    "name": "local_test",
                    "kind": "local_http",
                    "enabled": True,
                    "base_url": "http://127.0.0.1:9",
                    "endpoint": "/api/generate",
                    "model": "llama-test",
                    "timeout_seconds": 0.05,
                    "priority": 100,
                    "capabilities": ["hypothesis_generate"],
                }
            ]
        ),
    )

    ctx = multiprocessing.get_context("spawn")
    dispatcher = ctx.Process(
        target=_run_dispatcher_loop,
        daemon=True,
    )
    worker = ctx.Process(
        target=run_worker_loop,
        args=("hypothesis_workers",),
        daemon=True,
    )
    dispatcher.start()
    worker.start()
    try:
        publish_event(
            "signal_created",
            {
                "coin_id": coin_id,
                "timeframe": 15,
                "timestamp": event_timestamp,
                "signal_type": "bull_breakout",
            },
        )
        assert flush_publisher(timeout=5.0)

        redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await wait_until(
                lambda: {"hypothesis_created", "ai_insight"}
                <= {fields["event_type"] for _, fields in redis_client.xrange(settings.event_stream_name, "-", "+")},
                timeout=20.0,
                interval=0.2,
            )
            await async_db_session.rollback()
            hypotheses = await HypothesisQueryService(async_db_session).list_hypotheses(limit=5, coin_id=coin_id)
            assert hypotheses
            assert hypotheses[0].hypothesis_type == "signal_follow_through"
            assert hypotheses[0].provider == "heuristic"
            messages = redis_client.xrange(settings.event_stream_name, "-", "+")
            assert any(fields["event_type"] == "ai_insight" for _, fields in messages)
        finally:
            redis_client.close()
    finally:
        dispatcher.terminate()
        worker.terminate()
        dispatcher.join(timeout=2.0)
        worker.join(timeout=2.0)


@pytest.mark.asyncio
async def test_hypothesis_evaluation_job_persists_eval_and_weight(async_db_session, seeded_market, settings) -> None:
    coin_id = int(seeded_market["ETHUSD_EVT"]["coin_id"])
    candles = (
        (
            await async_db_session.execute(
                select(Candle)
                .where(Candle.coin_id == coin_id, Candle.timeframe == 15)
                .order_by(Candle.timestamp.asc())
            )
        )
        .scalars()
        .all()
    )
    hypothesis = AIHypothesis(
        coin_id=coin_id,
        timeframe=15,
        status="active",
        hypothesis_type="signal_follow_through",
        statement_json={"direction": "up", "target_move": 0.005, "assets": ["ETHUSD_EVT"]},
        confidence=0.62,
        horizon_min=60,
        eval_due_at=utc_now(),
        context_json={"trigger_timestamp": candles[-8].timestamp.isoformat()},
        provider="heuristic",
        model="rule-based",
        prompt_name="hypothesis.signal_created",
        prompt_version=1,
        source_event_type="signal_created",
        source_stream_id="1-0",
    )
    async_db_session.add(hypothesis)
    await async_db_session.commit()
    hypothesis_id = int(hypothesis.id)

    result = await evaluate_hypotheses_job()
    assert result["status"] == "ok"
    assert result["evaluated"] == 1

    assert flush_publisher(timeout=5.0)
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        stream_events = [fields["event_type"] for _, fields in redis_client.xrange(settings.event_stream_name, "-", "+")]
        assert "hypothesis_evaluated" in stream_events
        assert "ai_weights_updated" in stream_events
    finally:
        redis_client.close()

    await async_db_session.rollback()
    async_db_session.expire_all()
    evaluations = await HypothesisQueryService(async_db_session).list_evals(limit=5, hypothesis_id=hypothesis_id)
    weight = await async_db_session.scalar(
        select(AIWeight).where(AIWeight.scope == "hypothesis_type", AIWeight.weight_key == "signal_follow_through").limit(1)
    )
    hypothesis = await async_db_session.get(AIHypothesis, hypothesis_id)
    assert evaluations
    assert weight is not None
    assert hypothesis is not None
    assert hypothesis.status == "evaluated"
