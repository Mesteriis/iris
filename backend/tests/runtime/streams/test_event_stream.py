from __future__ import annotations

import multiprocessing
from datetime import timedelta

import pytest
from redis import Redis
from sqlalchemy import func, select

from src.core.db.session import SessionLocal
from src.runtime.control_plane.worker import create_topology_dispatcher_consumer
from src.runtime.streams.publisher import flush_publisher, publish_event
from src.runtime.streams.runner import run_worker_loop
from src.apps.market_data.models import Coin
from src.apps.market_data.support import publish_candle_events
from src.apps.signals.models import Signal
from tests.patterns_support import seed_pattern_catalog_metadata


def _run_topology_dispatcher() -> None:
    worker = create_topology_dispatcher_consumer()
    try:
        worker.run()
    finally:
        worker.close()


@pytest.mark.asyncio
async def test_polling_insert_publishes_candle_closed(seeded_market, settings, wait_until):
    sample_symbol = "BTCUSD_EVT"
    sample = seeded_market[sample_symbol]
    publish_candle_events(
        coin_id=int(sample["coin_id"]),
        timeframe=15,
        timestamp=sample["latest_timestamp"],
        created_count=220,
        source="polling_test",
    )
    assert flush_publisher(timeout=5.0)

    from redis import Redis

    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await wait_until(
            lambda: len(client.xrange(settings.event_stream_name, "-", "+")) >= 2,
            timeout=5.0,
            interval=0.1,
        )
        messages = client.xrange(settings.event_stream_name, "-", "+")
        event_types = [fields["event_type"] for _, fields in messages]
        assert "candle_inserted" in event_types
        assert "candle_closed" in event_types
    finally:
        client.close()


@pytest.mark.asyncio
async def test_event_stream_pipeline_creates_pattern_signals(seeded_market, settings, wait_until):
    db = SessionLocal()
    try:
        seed_pattern_catalog_metadata(db)
    finally:
        db.close()

    ctx = multiprocessing.get_context("spawn")
    dispatcher = ctx.Process(
        target=_run_topology_dispatcher,
        daemon=True,
    )
    indicator = ctx.Process(
        target=run_worker_loop,
        args=("indicator_workers",),
        daemon=True,
    )
    scheduler = ctx.Process(
        target=run_worker_loop,
        args=("analysis_scheduler_workers",),
        daemon=True,
    )
    pattern = ctx.Process(
        target=run_worker_loop,
        args=("pattern_workers",),
        daemon=True,
    )
    dispatcher.start()
    indicator.start()
    scheduler.start()
    pattern.start()
    try:
        for item in seeded_market.values():
            publish_event(
                "candle_closed",
                {
                    "coin_id": int(item["coin_id"]),
                    "timeframe": 15,
                    "timestamp": item["latest_timestamp"],
                    "source": "test_event_stream",
                },
            )
        assert flush_publisher(timeout=5.0)

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            def _pipeline_ready() -> bool:
                messages = client.xrange(settings.event_stream_name, "-", "+")
                event_types = {fields["event_type"] for _, fields in messages}
                return (
                    "candle_closed" in event_types
                    and "indicator_updated" in event_types
                    and "analysis_requested" in event_types
                    and ("pattern_detected" in event_types or "pattern_cluster_detected" in event_types)
                )

            await wait_until(_pipeline_ready, timeout=20.0, interval=0.2)

            db = SessionLocal()
            try:
                count = int(
                    db.scalar(
                        select(func.count())
                        .select_from(Signal)
                        .join(Coin, Coin.id == Signal.coin_id)
                        .where(
                            Coin.symbol.in_(sorted(seeded_market.keys())),
                            Signal.timeframe == 15,
                            Signal.signal_type.like("pattern_%"),
                        )
                    )
                    or 0
                )
                assert count > 0
            finally:
                db.close()

            messages = client.xrange(settings.event_stream_name, "-", "+")
            event_types = {fields["event_type"] for _, fields in messages}
            assert "candle_closed" in event_types
            assert "indicator_updated" in event_types
            assert "analysis_requested" in event_types
            assert "pattern_detected" in event_types or "pattern_cluster_detected" in event_types
        finally:
            client.close()
    finally:
        dispatcher.terminate()
        indicator.terminate()
        scheduler.terminate()
        pattern.terminate()
        dispatcher.join(timeout=2.0)
        indicator.join(timeout=2.0)
        scheduler.join(timeout=2.0)
        pattern.join(timeout=2.0)
