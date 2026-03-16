import multiprocessing
from datetime import UTC, datetime, timedelta, timezone

import pytest
from iris.core.settings import get_settings
from iris.runtime.streams.publisher import flush_publisher, publish_event
from redis import Redis

from tests.worker_helpers import crashing_worker_loop, recording_worker_loop


@pytest.mark.asyncio
async def test_multi_worker_ack_and_retry(redis_client: Redis, wait_until):
    settings = get_settings()
    stream_name = settings.event_stream_name
    group_name = "multi_worker_test"
    record_hash = "iris:test:worker-records"
    redis_client.delete(record_hash)

    ctx = multiprocessing.get_context("spawn")
    crash_worker = ctx.Process(
        target=crashing_worker_loop,
        kwargs={
            "stream_name": stream_name,
            "group_name": group_name,
            "consumer_name": "crash-worker",
            "interested_event_types": {"candle_closed"},
        },
        daemon=True,
    )
    crash_worker.start()
    publish_event(
        "candle_closed",
        {
            "coin_id": 9991,
            "timeframe": 15,
            "timestamp": "2026-03-11T13:45:00+00:00",
            "source": "multi_worker_test",
        },
    )
    assert flush_publisher(timeout=5.0)

    await wait_until(lambda: not crash_worker.is_alive(), timeout=5.0, interval=0.1)

    worker_a = ctx.Process(
        target=recording_worker_loop,
        kwargs={
            "stream_name": stream_name,
            "group_name": group_name,
            "consumer_name": "worker-a",
            "record_hash": record_hash,
            "interested_event_types": {"candle_closed"},
        },
        daemon=True,
    )
    worker_b = ctx.Process(
        target=recording_worker_loop,
        kwargs={
            "stream_name": stream_name,
            "group_name": group_name,
            "consumer_name": "worker-b",
            "record_hash": record_hash,
            "interested_event_types": {"candle_closed"},
        },
        daemon=True,
    )
    worker_a.start()
    worker_b.start()
    try:
        await wait_until(lambda: worker_a.is_alive() and worker_b.is_alive(), timeout=5.0, interval=0.1)

        base_timestamp = datetime(2026, 3, 11, 13, 45, tzinfo=UTC)
        for offset in range(1, 19):
            publish_event(
                "candle_closed",
                {
                    "coin_id": 9991 + offset,
                    "timeframe": 15,
                    "timestamp": (base_timestamp + timedelta(minutes=offset)).isoformat(),
                    "source": "multi_worker_test",
                },
            )
        assert flush_publisher(timeout=5.0)

        await wait_until(lambda: sum(int(v) for v in redis_client.hvals(record_hash) if str(v).isdigit()) >= 19, timeout=10.0, interval=0.2)

        counts = {key: int(value) for key, value in redis_client.hgetall(record_hash).items() if not key.startswith("last:")}
        assert counts.get("worker-a", 0) > 0
        assert counts.get("worker-b", 0) > 0
        pending = redis_client.xpending(stream_name, group_name)
        assert int(pending["pending"]) == 0
    finally:
        worker_a.terminate()
        worker_b.terminate()
        worker_a.join(timeout=2.0)
        worker_b.join(timeout=2.0)
        redis_client.delete(record_hash)
