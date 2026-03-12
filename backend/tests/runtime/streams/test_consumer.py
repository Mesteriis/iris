from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from redis.exceptions import RedisError, ResponseError

from src.runtime.streams import consumer
from src.runtime.streams.types import IrisEvent, build_event_fields


class _FakeAsyncRedis:
    def __init__(self) -> None:
        self.group_effects: list[object] = []
        self.autoclaim_effects: list[object] = []
        self.readgroup_effects: list[object] = []
        self.exists_effects: list[int] = []
        self.set_calls: list[tuple[str, str, int]] = []
        self.xack_calls: list[tuple[str, str, str]] = []
        self.closed = False

    async def xgroup_create(self, **kwargs: object) -> None:
        if self.group_effects:
            effect = self.group_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect

    async def set(self, key: str, value: str, ex: int) -> None:
        self.set_calls.append((key, value, ex))

    async def exists(self, _key: str) -> int:
        return self.exists_effects.pop(0)

    async def xautoclaim(self, **kwargs: object):
        effect = self.autoclaim_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect

    async def xreadgroup(self, **kwargs: object):
        effect = self.readgroup_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect

    async def xack(self, stream_name: str, group_name: str, message_id: str) -> None:
        self.xack_calls.append((stream_name, group_name, message_id))

    async def aclose(self) -> None:
        self.closed = True


def _build_fields(event_type: str = "candle_closed") -> dict[str, str]:
    return build_event_fields(
        event_type,
        {
            "coin_id": 7,
            "timeframe": 15,
            "timestamp": "2026-03-12T11:45:00+00:00",
            "source": "runtime_test",
        },
    )


@pytest.mark.asyncio
async def test_event_consumer_process_message_branches(monkeypatch) -> None:
    fake_redis = _FakeAsyncRedis()
    fake_redis.exists_effects = [1, 0, 0]
    handled: list[str] = []

    monkeypatch.setattr(consumer.Redis, "from_url", lambda *args, **kwargs: fake_redis)

    instance = consumer.EventConsumer(
        consumer.EventConsumerConfig(group_name="runtime-test", consumer_name="worker-a"),
        handler=lambda event: handled.append(event.event_type),
        interested_event_types={"candle_closed"},
    )

    await instance._process_message("1-0", _build_fields("candle_closed"))
    await instance._process_message("1-1", _build_fields("indicator_updated"))
    await instance._process_message("1-2", _build_fields("candle_closed"))

    assert fake_redis.xack_calls == [
        (instance._config.stream_name, "runtime-test", "1-0"),
        (instance._config.stream_name, "runtime-test", "1-1"),
        (instance._config.stream_name, "runtime-test", "1-2"),
    ]
    assert handled == ["candle_closed"]
    assert fake_redis.set_calls[0][0].startswith("iris:events:processed:runtime-test:")
    await instance.close_async()
    assert fake_redis.closed is True


@pytest.mark.asyncio
async def test_event_consumer_iteration_helpers_and_async_handler(monkeypatch) -> None:
    fake_redis = _FakeAsyncRedis()
    fake_redis.group_effects = [ResponseError("BUSYGROUP already exists"), None, None]
    fake_redis.autoclaim_effects = [
        ResponseError("NOGROUP consumer group missing"),
        RedisError("temporary failure"),
        ("0-0", [("2-0", _build_fields())], []),
    ]
    fake_redis.readgroup_effects = [
        ResponseError("NOGROUP consumer group missing"),
        [],
        [(consumer.EVENT_STREAM_NAME, [("3-0", _build_fields())])],
    ]
    handled: list[str] = []

    async def async_handler(event: IrisEvent) -> None:
        handled.append(event.event_type)

    monkeypatch.setattr(consumer.Redis, "from_url", lambda *args, **kwargs: fake_redis)
    instance = consumer.EventConsumer(
        consumer.EventConsumerConfig(group_name="runtime-test", consumer_name="worker-b"),
        handler=async_handler,
    )

    await instance._ensure_group()
    assert await instance._iter_stale_messages() == []
    assert await instance._iter_stale_messages() == []
    stale_messages = await instance._iter_stale_messages()
    assert stale_messages[0][0] == "2-0"

    assert await instance._iter_new_messages() == []
    assert await instance._iter_new_messages() == []
    new_messages = await instance._iter_new_messages()
    assert new_messages[0][0] == "3-0"

    event = consumer.parse_stream_message("4-0", _build_fields())
    await instance._invoke_handler(event)
    assert handled == ["candle_closed"]


@pytest.mark.asyncio
async def test_event_consumer_raise_paths_and_run_async_processing(monkeypatch) -> None:
    fake_redis = _FakeAsyncRedis()
    fake_redis.autoclaim_effects = [ResponseError("OTHER")]
    fake_redis.readgroup_effects = [ResponseError("OTHER")]

    monkeypatch.setattr(consumer.Redis, "from_url", lambda *args, **kwargs: fake_redis)
    instance = consumer.EventConsumer(
        consumer.EventConsumerConfig(group_name="runtime-test", consumer_name="worker-x"),
        handler=lambda event: None,
    )

    fake_redis.group_effects = [ResponseError("OTHER")]
    with pytest.raises(ResponseError, match="OTHER"):
        await instance._ensure_group()

    with pytest.raises(ResponseError, match="OTHER"):
        await instance._iter_stale_messages()

    with pytest.raises(ResponseError, match="OTHER"):
        await instance._iter_new_messages()

    processed: list[tuple[str, dict[str, str]]] = []

    async def ensure_noop() -> None:
        return None

    async def stale_empty() -> list[tuple[str, dict[str, str]]]:
        return []

    async def new_messages() -> list[tuple[str, dict[str, str]]]:
        return [("5-0", _build_fields())]

    async def process_message(message_id: str, fields: dict[str, str]) -> None:
        processed.append((message_id, fields))
        instance.stop()

    monkeypatch.setattr(instance, "_ensure_group", ensure_noop)
    monkeypatch.setattr(instance, "_iter_stale_messages", stale_empty)
    monkeypatch.setattr(instance, "_iter_new_messages", new_messages)
    monkeypatch.setattr(instance, "_process_message", process_message)

    await instance.run_async()

    assert processed[0][0] == "5-0"

    stale_processed: list[tuple[str, dict[str, str]]] = []

    async def stale_messages() -> list[tuple[str, dict[str, str]]]:
        return [("6-0", _build_fields())]

    async def process_stale(message_id: str, fields: dict[str, str]) -> None:
        stale_processed.append((message_id, fields))
        instance.stop()

    instance._stop_requested = False
    monkeypatch.setattr(instance, "_iter_stale_messages", stale_messages)
    monkeypatch.setattr(instance, "_process_message", process_stale)

    await instance.run_async()

    assert stale_processed[0][0] == "6-0"

    instance._stop_requested = False
    loop_checks = {"count": 0}

    async def new_empty() -> list[tuple[str, dict[str, str]]]:
        return []

    def stop_checker() -> bool:
        loop_checks["count"] += 1
        return loop_checks["count"] > 1

    monkeypatch.setattr(instance, "_iter_stale_messages", stale_empty)
    monkeypatch.setattr(instance, "_iter_new_messages", new_empty)

    await instance.run_async(stop_checker=stop_checker)

    assert loop_checks["count"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("error", "delay"), [(RedisError("boom"), 1.0), (RuntimeError("boom"), 0.5)])
async def test_event_consumer_run_async_error_branches(monkeypatch, error: Exception, delay: float) -> None:
    fake_redis = _FakeAsyncRedis()
    sleep_calls: list[float] = []

    async def failing_iter() -> list[tuple[str, dict[str, str]]]:
        raise error

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        instance.stop()

    monkeypatch.setattr(consumer.Redis, "from_url", lambda *args, **kwargs: fake_redis)
    monkeypatch.setattr(consumer.asyncio, "sleep", fake_sleep)

    instance = consumer.EventConsumer(
        consumer.EventConsumerConfig(group_name="runtime-test", consumer_name="worker-c"),
        handler=lambda event: None,
    )

    async def ensure_noop() -> None:
        return None

    monkeypatch.setattr(instance, "_ensure_group", ensure_noop)
    monkeypatch.setattr(instance, "_iter_stale_messages", failing_iter)

    await instance.run_async()

    assert sleep_calls == [delay]


def test_event_consumer_run_close_and_default_name(monkeypatch) -> None:
    fake_redis = _FakeAsyncRedis()
    captured: list[object] = []

    def fake_run(coro) -> None:
        captured.append(coro)
        coro.close()

    monkeypatch.setattr(consumer.Redis, "from_url", lambda *args, **kwargs: fake_redis)
    monkeypatch.setattr(consumer.asyncio, "run", fake_run)

    instance = consumer.EventConsumer(
        consumer.EventConsumerConfig(group_name="runtime-test", consumer_name="worker-d"),
        handler=lambda event: None,
    )
    instance.run(stop_checker=lambda: True)
    instance.close()

    assert len(captured) == 2
    assert consumer.default_consumer_name("runtime-test").startswith("runtime-test-")
