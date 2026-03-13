from __future__ import annotations

from types import SimpleNamespace

from redis.exceptions import RedisError

from src.runtime.streams import publisher


class _FakeRedis:
    def __init__(self) -> None:
        self.items: list[tuple[str, dict[str, str]]] = []
        self.closed = False
        self.raise_error = False

    def xadd(self, stream_name: str, fields: dict[str, str]) -> None:
        if self.raise_error:
            raise RedisError("publish failed")
        self.items.append((stream_name, fields))

    def close(self) -> None:
        self.closed = True


def test_event_publisher_flush_publish_and_reset(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    publisher._publisher = None

    monkeypatch.setattr(publisher.Redis, "from_url", lambda *args, **kwargs: fake_redis)
    monkeypatch.setattr(
        publisher,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://test", event_stream_name="iris:test:events"),
    )

    event_publisher = publisher.get_event_publisher()

    assert event_publisher.flush(timeout=0.1) is True

    publisher.publish_event(
        "candle_closed",
        {
            "coin_id": 7,
            "timeframe": 15,
            "timestamp": "2026-03-12T10:30:00+00:00",
            "source": "test",
        },
    )
    assert publisher.flush_publisher(timeout=1.0) is True
    assert fake_redis.items[0][0] == "iris:test:events"
    assert fake_redis.items[0][1]["event_type"] == "candle_closed"

    fake_redis.raise_error = True
    publisher.publish_event(
        "indicator_updated",
        {
            "coin_id": 7,
            "timeframe": 15,
            "timestamp": "2026-03-12T10:45:00+00:00",
        },
    )
    assert publisher.flush_publisher(timeout=1.0) is True

    event_publisher._stop_event.set()
    event_publisher._run()

    publisher.reset_event_publisher()
    publisher.reset_event_publisher()

    assert fake_redis.closed is True
    assert publisher._publisher is None


def test_event_publisher_run_handles_empty_queue(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    publisher._publisher = None

    monkeypatch.setattr(publisher.Redis, "from_url", lambda *args, **kwargs: fake_redis)

    event_publisher = publisher.RedisEventPublisher("redis://test", stream_name="iris:test:events")
    event_publisher._queue = type(
        "QueueStub",
        (),
        {
            "get": staticmethod(lambda timeout: (_ for _ in ()).throw(__import__("queue").Empty)),
            "put": staticmethod(lambda _item: None),
        },
    )()

    event_publisher._stop_event.set()
    event_publisher._run()
    event_publisher.close()


def test_flush_publisher_does_not_initialize_global_publisher() -> None:
    publisher._publisher = None
    assert publisher.flush_publisher(timeout=0.1) is True
    assert publisher._publisher is None


def test_event_publisher_close_tolerates_non_redis_stub(monkeypatch) -> None:
    publisher._publisher = None
    monkeypatch.setattr(publisher.Redis, "from_url", lambda *args, **kwargs: ("redis://test", True, object()))

    event_publisher = publisher.RedisEventPublisher("redis://test", stream_name="iris:test:events")
    event_publisher.close()
