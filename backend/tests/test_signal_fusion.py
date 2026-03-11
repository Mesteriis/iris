from __future__ import annotations

import json
import multiprocessing
from datetime import datetime, timezone

import pytest
from redis import Redis
from sqlalchemy import func, select

from app.analysis.signal_fusion_engine import evaluate_market_decision
from app.db.session import SessionLocal
from app.events.publisher import flush_publisher, publish_event
from app.events.runner import run_worker_loop
from app.models.market_decision import MarketDecision
from tests.fusion_support import create_test_coin, insert_signals, replace_pattern_statistics, upsert_coin_metrics


def test_signal_fusion_aggregates_bullish_stack_into_buy(db_session) -> None:
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    coin_id = int(coin.id)
    timestamp = datetime(2026, 3, 11, 13, 45, tzinfo=timezone.utc)
    upsert_coin_metrics(db_session, coin_id=coin_id, regime="bull_trend")
    replace_pattern_statistics(
        db_session,
        timeframe=15,
        rows=[
            ("bull_flag", "all", 0.72, 60),
            ("breakout_retest", "all", 0.69, 55),
            ("macd_cross", "all", 0.66, 80),
        ],
    )
    insert_signals(
        db_session,
        coin_id=coin_id,
        timeframe=15,
        candle_timestamp=timestamp,
        items=[
            ("pattern_bull_flag", 0.82),
            ("pattern_breakout_retest", 0.77),
            ("pattern_macd_cross", 0.74),
        ],
    )

    result = evaluate_market_decision(
        db_session,
        coin_id=coin_id,
        timeframe=15,
        trigger_timestamp=timestamp,
        emit_event=False,
    )

    assert result["status"] == "ok"
    assert result["decision"] == "BUY"
    assert float(result["confidence"]) >= 0.45
    latest = db_session.scalar(
        select(MarketDecision)
        .where(MarketDecision.coin_id == coin_id, MarketDecision.timeframe == 15)
        .order_by(MarketDecision.created_at.desc(), MarketDecision.id.desc())
        .limit(1)
    )
    assert latest is not None
    assert latest.decision == "BUY"
    assert int(latest.signal_count) == 3


@pytest.mark.asyncio
async def test_signal_fusion_worker_publishes_decision_event(db_session, settings, wait_until):
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    coin_id = int(coin.id)
    timestamp = datetime(2026, 3, 11, 13, 45, tzinfo=timezone.utc)
    db = SessionLocal()
    try:
        upsert_coin_metrics(db, coin_id=coin_id, regime="bull_trend")
        replace_pattern_statistics(
            db,
            timeframe=15,
            rows=[
                ("bull_flag", "all", 0.71, 50),
                ("breakout_retest", "all", 0.67, 50),
            ],
        )
        insert_signals(
            db,
            coin_id=coin_id,
            timeframe=15,
            candle_timestamp=timestamp,
            items=[
                ("pattern_bull_flag", 0.81),
                ("pattern_breakout_retest", 0.79),
            ],
        )
    finally:
        db.close()

    ctx = multiprocessing.get_context("spawn")
    worker = ctx.Process(
        target=run_worker_loop,
        args=("signal_fusion_workers",),
        daemon=True,
    )
    worker.start()
    try:
        publish_event(
            "signal_created",
            {
                "coin_id": coin_id,
                "timeframe": 15,
                "timestamp": timestamp,
                "signal_type": "pattern_bull_flag",
            },
        )
        assert flush_publisher(timeout=5.0)

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            def _decision_event_ready() -> bool:
                for _, fields in client.xrange(settings.event_stream_name, "-", "+"):
                    if fields.get("event_type") != "decision_generated":
                        continue
                    payload = json.loads(fields.get("payload", "{}"))
                    if payload.get("source") == "signal_fusion":
                        return True
                return False

            await wait_until(_decision_event_ready, timeout=10.0, interval=0.2)
        finally:
            client.close()

        db = SessionLocal()
        try:
            count = int(
                db.scalar(
                    select(func.count())
                    .select_from(MarketDecision)
                    .where(MarketDecision.coin_id == coin_id, MarketDecision.timeframe == 15)
                )
                or 0
            )
            assert count > 0
        finally:
            db.close()
    finally:
        worker.terminate()
        worker.join(timeout=2.0)
