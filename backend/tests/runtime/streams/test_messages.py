from datetime import UTC, datetime, timezone
from types import SimpleNamespace

import pytest
from iris.runtime.streams import messages
from redis.exceptions import RedisError, ResponseError


class _FakeRedis:
    def __init__(self) -> None:
        self.group_create_calls: list[dict[str, object]] = []
        self.group_create_effects: list[object] = []
        self.read_effects: list[object] = []
        self.ack_calls: list[tuple[str, str, str]] = []
        self.ack_effects: list[object] = []
        self.xadd_calls: list[tuple[str, dict[str, str]]] = []
        self.delconsumer_calls: list[tuple[str, str, str]] = []
        self.delconsumer_effects: list[object] = []
        self.closed = False
        self.bus: messages.RedisMessageBus | None = None

    def xgroup_create(self, **kwargs: object) -> None:
        self.group_create_calls.append(kwargs)
        if self.group_create_effects:
            effect = self.group_create_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect

    def xreadgroup(self, **kwargs: object):
        effect = self.read_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect

    def xack(self, stream_name: str, group_name: str, message_id: str) -> None:
        self.ack_calls.append((stream_name, group_name, message_id))
        if self.bus is not None:
            self.bus._stop_event.set()
        if self.ack_effects:
            effect = self.ack_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect

    def xadd(self, stream_name: str, fields: dict[str, str]) -> None:
        self.xadd_calls.append((stream_name, fields))

    def xgroup_delconsumer(self, *, name: str, groupname: str, consumername: str) -> None:
        self.delconsumer_calls.append((name, groupname, consumername))
        if self.delconsumer_effects:
            effect = self.delconsumer_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect

    def close(self) -> None:
        self.closed = True


class _FakeThread:
    def __init__(self, *, target=None, args=(), daemon: bool = False, name: str | None = None) -> None:
        self.target = target
        self.args = args
        self.daemon = daemon
        self.name = name
        self.started = False
        self.joined = False

    def start(self) -> None:
        self.started = True

    def join(self, timeout: float | None = None) -> None:
        self.joined = True


def _make_bus(monkeypatch, fake_redis: _FakeRedis) -> messages.RedisMessageBus:
    monkeypatch.setattr(messages.Redis, "from_url", lambda *args, **kwargs: fake_redis)
    monkeypatch.setattr(messages.threading, "Thread", _FakeThread)
    bus = messages.RedisMessageBus("redis://test", stream_name="iris:test:messages")
    fake_redis.bus = bus
    return bus


def test_message_bus_deserialize_publish_and_receivers(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    bus = _make_bus(monkeypatch, fake_redis)
    fake_redis.group_create_effects = [ResponseError("BUSYGROUP already exists")]

    message = bus._deserialize_message(
        {
            "topic": "coin.history.progress",
            "text": "history loaded",
            "coin_symbol": "BTCUSD",
            "payload": "[]",
        }
    )
    assert message.topic == "coin.history.progress"
    assert message.payload == {}
    bus._ensure_group("frontend")

    bus.publish(
        messages.AnalysisMessage(
            topic="coin.history.progress",
            text="loaded",
            coin_symbol="BTCUSD",
            created_at=datetime(2026, 3, 12, 11, 0, tzinfo=UTC),
            payload={"progress": 50},
        )
    )
    queued = bus._publish_queue.get_nowait()
    assert queued["topic"] == "coin.history.progress"
    assert queued["payload"] == '{"progress": 50}'

    bus.start_console_receiver("frontend")
    bus.start_console_receiver("frontend")

    assert len(bus._threads) == 1
    assert fake_redis.group_create_calls[0]["groupname"] == "frontend"


def test_message_bus_publish_loop_and_close(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    fake_redis.delconsumer_effects = [RedisError("gone")]
    bus = _make_bus(monkeypatch, fake_redis)

    bus.start_console_receiver("frontend")
    bus._publish_queue.put(
        {
            "topic": "coin.history.progress",
            "text": "loaded",
            "coin_symbol": "BTCUSD",
            "created_at": "2026-03-12T11:00:00+00:00",
            "payload": "{}",
        }
    )
    bus._publish_queue.put(None)

    bus._publish_loop()
    bus.close()

    assert fake_redis.xadd_calls[0][0] == "iris:test:messages"
    assert fake_redis.closed is True


def test_message_bus_consume_group_recovers_and_acks(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    fake_redis.read_effects = [
        ResponseError("NOGROUP missing"),
        [
            (
                "iris:test:messages",
                [
                    (
                        "1-0",
                        {
                            "topic": "coin.history.progress",
                            "text": "loaded",
                            "coin_symbol": "BTCUSD",
                            "created_at": "2026-03-12T11:00:00+00:00",
                            "payload": "{}",
                        },
                    )
                ],
            )
        ],
    ]
    bus = _make_bus(monkeypatch, fake_redis)

    bus._consume_group("frontend", "frontend", "consumer-a")

    assert len(fake_redis.group_create_calls) >= 1
    assert fake_redis.ack_calls == [("iris:test:messages", "frontend", "1-0")]


def test_message_bus_consume_group_handles_reader_and_handler_failures(monkeypatch) -> None:
    fake_reader_redis = _FakeRedis()
    fake_reader_redis.read_effects = [RedisError("read failed")]
    reader_bus = _make_bus(monkeypatch, fake_reader_redis)
    monkeypatch.setattr(messages.time, "sleep", lambda _seconds: reader_bus._stop_event.set())

    reader_bus._consume_group("frontend", "frontend", "consumer-b")

    fake_handler_redis = _FakeRedis()
    fake_handler_redis.ack_effects = [RedisError("ack failed")]
    fake_handler_redis.read_effects = [[("iris:test:messages", [("2-0", {"topic": "broken"})])]]
    handler_bus = _make_bus(monkeypatch, fake_handler_redis)

    handler_bus._consume_group("frontend", "frontend", "consumer-c")

    assert fake_handler_redis.ack_calls == [("iris:test:messages", "frontend", "2-0")]


def test_message_bus_raise_and_empty_paths(monkeypatch) -> None:
    fake_raise_redis = _FakeRedis()
    fake_raise_redis.group_create_effects = [ResponseError("OTHER")]
    bus = _make_bus(monkeypatch, fake_raise_redis)

    with pytest.raises(ResponseError, match="OTHER"):
        bus._ensure_group("frontend")

    empty_redis = _FakeRedis()
    empty_redis.read_effects = [[], [("iris:test:messages", [("3-0", {"topic": "broken"})])]]
    empty_bus = _make_bus(monkeypatch, empty_redis)
    empty_bus._consume_group("frontend", "frontend", "consumer-empty")

    recovery_redis = _FakeRedis()
    recovery_redis.read_effects = [ResponseError("NOGROUP missing")]
    recovery_bus = _make_bus(monkeypatch, recovery_redis)

    def failing_ensure_group(_group_name: str) -> None:
        raise RedisError("recovery failed")

    monkeypatch.setattr(recovery_bus, "_ensure_group", failing_ensure_group)
    monkeypatch.setattr(messages.time, "sleep", lambda _seconds: recovery_bus._stop_event.set())
    recovery_bus._consume_group("frontend", "frontend", "consumer-recovery")

    empty_bus._stop_event.set()
    empty_bus._publish_loop()

    class EmptyQueue:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, timeout: float):
            del timeout
            self.calls += 1
            empty_bus._stop_event.set()
            raise __import__("queue").Empty

        def put(self, _value) -> None:
            return None

    empty_bus._stop_event.clear()
    empty_bus._publish_queue = EmptyQueue()
    empty_bus._publish_loop()


def test_message_bus_singleton_helpers(monkeypatch) -> None:
    created: list[str] = []
    started: list[str] = []
    closed: list[str] = []

    class FakeBus:
        def __init__(self, redis_url: str) -> None:
            created.append(redis_url)

        def start_console_receiver(self, receiver_name: str) -> None:
            started.append(receiver_name)

        def close(self) -> None:
            closed.append("closed")

    messages._message_bus = None
    monkeypatch.setattr(messages, "RedisMessageBus", FakeBus)
    monkeypatch.setattr(messages, "get_settings", lambda: SimpleNamespace(redis_url="redis://singleton"))

    bus = messages.get_message_bus()
    assert bus is messages.get_message_bus()

    messages.register_default_receivers()
    messages.reset_message_bus()

    assert created == ["redis://singleton"]
    assert started == ["frontend", "ha"]
    assert closed == ["closed"]
    assert messages._message_bus is None

    messages.reset_message_bus()


def test_message_bus_publish_helpers(monkeypatch) -> None:
    published: list[messages.AnalysisMessage] = []

    class FakeBus:
        def publish(self, message: messages.AnalysisMessage) -> None:
            published.append(message)

    coin = SimpleNamespace(id=7, symbol="BTCUSD", name="Bitcoin", asset_type="crypto")
    monkeypatch.setattr(messages, "get_message_bus", lambda: FakeBus())

    messages.publish_coin_history_progress_message(
        coin,
        progress_percent=25.0,
        loaded_points=250,
        total_points=1000,
    )
    messages.publish_coin_history_loaded_message(coin, total_points=1000)
    messages.publish_coin_analysis_messages(coin)
    messages.publish_investment_decision_message(
        coin,
        timeframe=15,
        decision="BUY",
        confidence=0.81,
        score=7.2,
        reason="trend",
    )
    messages.publish_investment_signal_message(
        coin,
        timeframe=60,
        decision="HOLD",
        confidence=0.55,
        risk_score=0.12,
        reason="range",
    )

    assert [message.topic for message in published] == [
        "coin.history.progress",
        "coin.history.loaded",
        "coin.ready_for_analysis",
        "analysis.started",
        "iris.decision",
        "iris.investment_signal",
    ]
    assert published[0].payload["coin_name"] == "Bitcoin"
    assert published[-1].payload["risk_adjusted_score"] == 0.12
