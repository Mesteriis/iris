from __future__ import annotations

import multiprocessing

import pytest
from redis import Redis
from sqlalchemy import select

from src.apps.hypothesis_engine.models import AIHypothesis, AIHypothesisEval, AIWeight
from src.apps.hypothesis_engine.tasks.hypothesis_tasks import evaluate_hypotheses_job
from src.apps.market_data.domain import utc_now
from src.apps.market_data.models import Candle
from src.core.db.session import SessionLocal
from src.runtime.streams.publisher import flush_publisher, publish_event
from src.runtime.streams.runner import run_worker_loop


@pytest.mark.asyncio
async def test_signal_created_pipeline_persists_and_publishes_hypothesis(seeded_market, settings, wait_until) -> None:
    coin_id = int(seeded_market["ETHUSD_EVT"]["coin_id"])
    event_timestamp = seeded_market["ETHUSD_EVT"]["latest_timestamp"]

    ctx = multiprocessing.get_context("spawn")
    worker = ctx.Process(
        target=run_worker_loop,
        args=("hypothesis_workers",),
        daemon=True,
    )
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
                lambda: any(
                    fields["event_type"] == "hypothesis_created"
                    for _, fields in redis_client.xrange(settings.event_stream_name, "-", "+")
                ),
                timeout=20.0,
                interval=0.2,
            )
            db = SessionLocal()
            try:
                hypothesis = (
                    db.execute(
                        select(AIHypothesis)
                        .where(AIHypothesis.coin_id == coin_id)
                        .order_by(AIHypothesis.created_at.desc(), AIHypothesis.id.desc())
                    )
                ).scalars().first()
                assert hypothesis is not None
                assert hypothesis.hypothesis_type == "signal_follow_through"
                assert hypothesis.provider == "heuristic"
                messages = redis_client.xrange(settings.event_stream_name, "-", "+")
                assert any(fields["event_type"] == "ai_insight" for _, fields in messages)
            finally:
                db.close()
        finally:
            redis_client.close()
    finally:
        worker.terminate()
        worker.join(timeout=2.0)


@pytest.mark.asyncio
async def test_hypothesis_evaluation_job_persists_eval_and_weight(seeded_market, settings) -> None:
    coin_id = int(seeded_market["ETHUSD_EVT"]["coin_id"])
    db = SessionLocal()
    try:
        candles = (
            db.execute(
                select(Candle)
                .where(Candle.coin_id == coin_id, Candle.timeframe == 15)
                .order_by(Candle.timestamp.asc())
            )
        ).scalars().all()
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
        db.add(hypothesis)
        db.commit()
        hypothesis_id = int(hypothesis.id)
    finally:
        db.close()

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

    db = SessionLocal()
    try:
        evaluation = db.scalar(select(AIHypothesisEval).where(AIHypothesisEval.hypothesis_id == hypothesis_id).limit(1))
        weight = db.scalar(select(AIWeight).where(AIWeight.scope == "hypothesis_type", AIWeight.weight_key == "signal_follow_through").limit(1))
        hypothesis = db.get(AIHypothesis, hypothesis_id)
        assert evaluation is not None
        assert weight is not None
        assert hypothesis is not None
        assert hypothesis.status == "evaluated"
    finally:
        db.close()
