from datetime import datetime, timezone

import pytest

from src.apps.control_plane.cache import TopologyCacheManager, TopologySnapshotCodec
from src.apps.control_plane.contracts import EventConsumerSnapshot, EventDefinitionSnapshot, TopologySnapshot
from src.runtime.streams.types import IrisEvent


class FakeAsyncCache:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.storage.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        del ex
        self.storage[key] = value

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.storage.pop(key, None)


def _snapshot(version_number: int) -> TopologySnapshot:
    return TopologySnapshot(
        version_number=version_number,
        created_at=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
        events={"signal_created": EventDefinitionSnapshot(event_type="signal_created", domain="signals")},
        consumers={
            "hypothesis_workers": EventConsumerSnapshot(
                consumer_key="hypothesis_workers",
                delivery_stream="iris:deliveries:hypothesis_workers",
                compatible_event_types=("signal_created",),
            )
        },
        routes_by_event_type={},
        coin_symbol_by_id={1: "BTCUSD"},
        coin_exchange_by_id={1: "binance"},
    )


@pytest.mark.asyncio
async def test_topology_snapshot_codec_round_trip() -> None:
    snapshot = _snapshot(4)

    raw = TopologySnapshotCodec.dump(snapshot)
    restored = TopologySnapshotCodec.load(raw)

    assert restored.version_number == 4
    assert restored.coin_symbol_by_id == {1: "BTCUSD"}
    assert restored.consumers["hypothesis_workers"].delivery_stream.endswith("hypothesis_workers")


@pytest.mark.asyncio
async def test_topology_cache_manager_prefers_local_then_redis() -> None:
    calls = {"count": 0}

    class Loader:
        async def load(self) -> TopologySnapshot:
            calls["count"] += 1
            return _snapshot(1)

    cache = FakeAsyncCache()
    manager = TopologyCacheManager(loader=Loader(), cache_client=cache)

    first = await manager.get_snapshot()
    second = await manager.get_snapshot()
    manager2 = TopologyCacheManager(loader=Loader(), cache_client=cache)
    third = await manager2.get_snapshot()

    assert first.version_number == 1
    assert second.version_number == 1
    assert third.version_number == 1
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_topology_cache_manager_refreshes_on_control_event() -> None:
    versions = iter([_snapshot(1), _snapshot(2)])

    class Loader:
        async def load(self) -> TopologySnapshot:
            return next(versions)

    cache = FakeAsyncCache()
    manager = TopologyCacheManager(loader=Loader(), cache_client=cache)
    initial = await manager.get_snapshot()
    refreshed = await manager.refresh_from_control_event(
        IrisEvent(
            stream_id="1-0",
            event_type="control.cache_invalidated",
            coin_id=0,
            timeframe=0,
            timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
            payload={},
        )
    )

    assert initial.version_number == 1
    assert refreshed is not None
    assert refreshed.version_number == 2
