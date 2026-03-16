import multiprocessing
from datetime import datetime, timedelta, timezone

import pytest
from redis import Redis

from src.core.settings import get_settings
from src.runtime.control_plane.worker import create_topology_dispatcher_consumer
from src.runtime.streams.publisher import flush_publisher, publish_event
from src.runtime.streams.runner import run_worker_loop
from src.apps.patterns.domain.scheduler import (
    analysis_interval,
    assign_activity_bucket,
    calculate_activity_score,
    should_request_analysis,
)


def _run_topology_dispatcher() -> None:
    worker = create_topology_dispatcher_consumer()
    try:
        worker.run()
    finally:
        worker.close()


def test_activity_score_and_bucket_assignment() -> None:
    hot_score = calculate_activity_score(
        price_change_24h=18,
        volatility=12,
        volume_change_24h=45,
        price_current=100,
    )
    warm_score = calculate_activity_score(
        price_change_24h=8,
        volatility=6,
        volume_change_24h=30,
        price_current=100,
    )
    cold_score = calculate_activity_score(
        price_change_24h=4,
        volatility=3,
        volume_change_24h=12,
        price_current=100,
    )
    dead_score = calculate_activity_score(
        price_change_24h=1,
        volatility=1,
        volume_change_24h=4,
        price_current=100,
    )

    assert hot_score > 70
    assert assign_activity_bucket(hot_score) == "HOT"
    assert 40 <= warm_score <= 70
    assert assign_activity_bucket(warm_score) == "WARM"
    assert 15 <= cold_score < 40
    assert assign_activity_bucket(cold_score) == "COLD"
    assert dead_score < 15
    assert assign_activity_bucket(dead_score) == "DEAD"


def test_scheduler_decisions_by_bucket() -> None:
    timestamp = datetime(2026, 3, 11, 14, 0, tzinfo=timezone.utc)
    assert should_request_analysis(
        timeframe=15,
        timestamp=timestamp,
        activity_bucket="HOT",
        last_analysis_at=timestamp - timedelta(minutes=15),
    )
    assert not should_request_analysis(
        timeframe=15,
        timestamp=timestamp,
        activity_bucket="WARM",
        last_analysis_at=timestamp - timedelta(minutes=15),
    )
    assert should_request_analysis(
        timeframe=15,
        timestamp=timestamp,
        activity_bucket="WARM",
        last_analysis_at=timestamp - analysis_interval("WARM", 15),
    )
    assert not should_request_analysis(
        timeframe=15,
        timestamp=timestamp,
        activity_bucket="COLD",
        last_analysis_at=timestamp - timedelta(minutes=45),
    )
    assert should_request_analysis(
        timeframe=15,
        timestamp=timestamp,
        activity_bucket="DEAD",
        last_analysis_at=timestamp - timedelta(hours=1),
    )


@pytest.mark.asyncio
async def test_scheduler_worker_emits_analysis_requested(seeded_market, wait_until) -> None:
    settings = get_settings()
    sample = seeded_market["BTCUSD_EVT"]
    ctx = multiprocessing.get_context("spawn")
    dispatcher = ctx.Process(
        target=_run_topology_dispatcher,
        daemon=True,
    )
    scheduler = ctx.Process(
        target=run_worker_loop,
        args=("analysis_scheduler_workers",),
        daemon=True,
    )
    dispatcher.start()
    scheduler.start()
    try:
        publish_event(
            "indicator_updated",
            {
                "coin_id": int(sample["coin_id"]),
                "timeframe": 15,
                "timestamp": sample["latest_timestamp"],
                "activity_score": 88.0,
                "activity_bucket": "HOT",
                "analysis_priority": 100,
                "market_regime": "bull_trend",
                "regime_confidence": 0.84,
            },
        )
        assert flush_publisher(timeout=5.0)

        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await wait_until(
                lambda: any(
                    fields.get("event_type") == "analysis_requested"
                    for _, fields in redis.xrange(settings.event_stream_name, "-", "+")
                ),
                timeout=8.0,
                interval=0.2,
            )
        finally:
            redis.close()
    finally:
        dispatcher.terminate()
        scheduler.terminate()
        dispatcher.join(timeout=2.0)
        scheduler.join(timeout=2.0)
