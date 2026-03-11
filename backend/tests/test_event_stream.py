from __future__ import annotations

import multiprocessing
from datetime import timedelta

import pytest
from redis import Redis
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.events.publisher import flush_publisher, publish_event
from app.events.runner import run_worker_loop
from app.models.coin import Coin
from app.models.signal import Signal
from app.services.history_loader import publish_candle_events
from app.services.market_data import ensure_utc


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
    ctx = multiprocessing.get_context("spawn")
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

        def _signals_ready() -> bool:
            db = SessionLocal()
            try:
                for symbol, item in seeded_market.items():
                    signal_timestamp = ensure_utc(item["latest_timestamp"]) + timedelta(minutes=15)
                    count = int(
                        db.scalar(
                            select(func.count())
                            .select_from(Signal)
                            .join(Coin, Coin.id == Signal.coin_id)
                            .where(
                                Coin.symbol == symbol,
                                Signal.timeframe == 15,
                                Signal.candle_timestamp == signal_timestamp,
                                Signal.signal_type.like("pattern_%"),
                            )
                        )
                        or 0
                    )
                    if count <= 0:
                        return False
                return True
            finally:
                db.close()

        await wait_until(_signals_ready, timeout=12.0, interval=0.2)

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            messages = client.xrange(settings.event_stream_name, "-", "+")
            event_types = {fields["event_type"] for _, fields in messages}
            assert "candle_closed" in event_types
            assert "indicator_updated" in event_types
            assert "analysis_requested" in event_types
            assert "pattern_detected" in event_types or "pattern_cluster_detected" in event_types
        finally:
            client.close()
    finally:
        indicator.terminate()
        scheduler.terminate()
        pattern.terminate()
        indicator.join(timeout=2.0)
        scheduler.join(timeout=2.0)
        pattern.join(timeout=2.0)
