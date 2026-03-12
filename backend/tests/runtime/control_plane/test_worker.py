from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.apps.control_plane.contracts import (
    EventConsumerSnapshot,
    EventDefinitionSnapshot,
    EventRouteSnapshot,
    TopologySnapshot,
)
from src.apps.control_plane.enums import EventRouteScope, EventRouteStatus
from src.runtime.control_plane.worker import TopologyDispatchService, build_delivery_stream_name
from src.runtime.streams.types import IrisEvent


def _snapshot() -> TopologySnapshot:
    route = EventRouteSnapshot(
        route_key="signal_created:hypothesis_workers:global:*:*",
        event_type="signal_created",
        consumer_key="hypothesis_workers",
        status=EventRouteStatus.ACTIVE,
        scope_type=EventRouteScope.GLOBAL,
    )
    return TopologySnapshot(
        version_number=3,
        created_at=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
        events={"signal_created": EventDefinitionSnapshot(event_type="signal_created", domain="signals")},
        consumers={
            "hypothesis_workers": EventConsumerSnapshot(
                consumer_key="hypothesis_workers",
                delivery_stream="iris:deliveries:hypothesis_workers",
                compatible_event_types=("signal_created",),
            )
        },
        routes_by_event_type={"signal_created": (route,)},
    )


def test_build_delivery_stream_name() -> None:
    assert build_delivery_stream_name("portfolio_workers") == "iris:deliveries:portfolio_workers"


@pytest.mark.asyncio
async def test_topology_dispatch_service_uses_cache_manager_and_refreshes_control_events() -> None:
    class CacheManager:
        def __init__(self) -> None:
            self.refresh_calls = 0
            self.snapshot_calls = 0

        async def get_snapshot(self, *, force_refresh: bool = False) -> TopologySnapshot:
            del force_refresh
            self.snapshot_calls += 1
            return _snapshot()

        async def refresh_from_control_event(self, event: IrisEvent) -> TopologySnapshot:
            del event
            self.refresh_calls += 1
            return _snapshot()

    class Publisher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def publish(self, *, route, consumer, event, shadow) -> None:
            del event, shadow
            self.calls.append((route.route_key, consumer.consumer_key))

        async def close(self) -> None:
            return None

    cache = CacheManager()
    publisher = Publisher()
    service = TopologyDispatchService(cache_manager=cache, publisher=publisher, environment="development")

    result = await service.handle_event(
        IrisEvent(
            stream_id="1-0",
            event_type="control.cache_invalidated",
            coin_id=0,
            timeframe=0,
            timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
            payload={},
        )
    )
    await service.handle_event(
        IrisEvent(
            stream_id="2-0",
            event_type="signal_created",
            coin_id=1,
            timeframe=15,
            timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
            payload={},
        )
    )

    assert result["version_number"] == 3
    assert cache.refresh_calls == 1
    assert cache.snapshot_calls == 2
    assert publisher.calls == [("signal_created:hypothesis_workers:global:*:*", "hypothesis_workers")]
