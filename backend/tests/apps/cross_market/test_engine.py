from __future__ import annotations

import json
import multiprocessing
from datetime import timedelta

import pytest
from redis import Redis
from sqlalchemy import select
from src.apps.cross_market.models import CoinRelation
from src.apps.indicators.models import CoinMetrics
from src.apps.predictions.models import MarketPrediction
from src.core.db.session import SessionLocal
from src.runtime.control_plane.worker import create_topology_dispatcher_consumer
from src.runtime.streams.publisher import flush_publisher, publish_event
from src.runtime.streams.runner import run_worker_loop

from tests.cross_market_support import (
    DEFAULT_START,
    correlated_close_series,
    create_cross_market_coin,
    generate_close_series,
    seed_candles,
    set_market_metrics,
)


def _run_dispatcher_loop() -> None:
    consumer = create_topology_dispatcher_consumer()
    try:
        consumer.run()
    finally:
        consumer.close()


def _start_cross_market_pipeline_processes() -> tuple[multiprocessing.Process, multiprocessing.Process]:
    ctx = multiprocessing.get_context("spawn")
    dispatcher = ctx.Process(target=_run_dispatcher_loop, daemon=True)
    worker = ctx.Process(
        target=run_worker_loop,
        args=("cross_market_workers",),
        daemon=True,
    )
    dispatcher.start()
    worker.start()
    return dispatcher, worker


def _stop_processes(*processes: multiprocessing.Process) -> None:
    for process in processes:
        process.terminate()
    for process in processes:
        process.join(timeout=2.0)


@pytest.mark.asyncio
async def test_cross_market_worker_updates_relations_and_detects_market_leader(db_session, settings, wait_until) -> None:
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
    leader_returns = [
        0.01 if index % 12 in {1, 2, 3}
        else -0.007 if index % 12 in {8, 9}
        else 0.002
        for index in range(220)
    ]
    leader_closes = generate_close_series(start_price=110.0, returns=leader_returns)
    follower_closes = correlated_close_series(
        leader_returns=leader_returns,
        lag_bars=4,
        start_price=62.0,
    )
    seed_candles(db_session, coin=leader, interval="1h", closes=leader_closes, start=DEFAULT_START)
    seed_candles(db_session, coin=follower, interval="1h", closes=follower_closes, start=DEFAULT_START)
    leader_metrics = set_market_metrics(
        db_session,
        coin_id=int(leader.id),
        regime="bull_trend",
        price_change_24h=7.1,
        volume_change_24h=34.0,
        volatility=0.08,
        market_cap=950_000_000_000.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(follower.id),
        regime="bull_trend",
        price_change_24h=4.2,
        volume_change_24h=19.0,
        volatility=0.05,
        market_cap=420_000_000_000.0,
    )
    leader_metrics.activity_bucket = "HOT"
    db_session.commit()

    last_timestamp = DEFAULT_START + timedelta(hours=len(follower_closes) - 1)
    dispatcher, worker = _start_cross_market_pipeline_processes()
    try:
        publish_event(
            "candle_closed",
            {
                "coin_id": int(follower.id),
                "timeframe": 60,
                "timestamp": last_timestamp,
                "source": "test_cross_market",
            },
        )
        publish_event(
            "indicator_updated",
            {
                "coin_id": int(leader.id),
                "timeframe": 60,
                "timestamp": last_timestamp,
                "activity_bucket": "HOT",
                "price_change_24h": 7.1,
                "market_regime": "bull_trend",
            },
        )
        assert flush_publisher(timeout=5.0)

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            def _pipeline_ready() -> bool:
                event_types = []
                for _, fields in client.xrange(settings.event_stream_name, "-", "+"):
                    event_types.append(fields.get("event_type"))
                return "correlation_updated" in event_types and "market_leader_detected" in event_types

            await wait_until(_pipeline_ready, timeout=15.0, interval=0.2)
            messages = client.xrange(settings.event_stream_name, "-", "+")
            leader_payloads = [
                json.loads(fields.get("payload") or "{}")
                for _, fields in messages
                if fields.get("event_type") == "market_leader_detected"
            ]
            assert any(int(payload.get("leader_coin_id") or 0) == int(leader.id) for payload in leader_payloads)
        finally:
            client.close()

        verification_db = SessionLocal()
        try:
            relation = verification_db.scalar(
                select(CoinRelation)
                .where(
                    CoinRelation.leader_coin_id == int(leader.id),
                    CoinRelation.follower_coin_id == int(follower.id),
                )
                .limit(1)
            )
            prediction = verification_db.scalar(
                select(MarketPrediction)
                .where(
                    MarketPrediction.leader_coin_id == int(leader.id),
                    MarketPrediction.target_coin_id == int(follower.id),
                    MarketPrediction.status == "pending",
                )
                .order_by(MarketPrediction.created_at.desc(), MarketPrediction.id.desc())
                .limit(1)
            )
            assert relation is not None
            assert float(relation.confidence) >= 0.5
            assert prediction is not None
            assert prediction.prediction_event == "leader_breakout"
        finally:
            verification_db.close()
    finally:
        _stop_processes(dispatcher, worker)
