from datetime import UTC, datetime, timezone

from iris.apps.control_plane.contracts import RouteFilters, RouteShadow, RouteThrottle
from iris.apps.control_plane.engines import (
    command_from_payload,
    preview_topology_diff,
    route_snapshot_from_command,
    route_to_snapshot,
)
from iris.apps.control_plane.enums import EventRouteScope, EventRouteStatus, TopologyDraftChangeType
from iris.apps.control_plane.read_models import EventRouteReadModel, TopologyDraftChangeReadModel


def test_route_engine_normalizes_command_payload() -> None:
    command = command_from_payload(
        {
            "event_type": "signal_created",
            "consumer_key": "hypothesis_workers",
            "status": EventRouteStatus.SHADOW.value,
            "scope_type": EventRouteScope.SYMBOL.value,
            "scope_value": "BTCUSD",
            "environment": "development",
            "filters": {"symbol": ["BTCUSD", "BTCUSD"], "timeframe": [60, 60]},
            "throttle": {"limit": 2, "window_seconds": 120},
            "shadow": {"enabled": True, "sample_rate": 0.25, "observe_only": True},
            "notes": "Shadow BTC route",
            "priority": 123,
            "system_managed": True,
        }
    )

    snapshot = route_to_snapshot(route_snapshot_from_command(command))

    assert command.route_key == "signal_created:hypothesis_workers:symbol:BTCUSD:development"
    assert snapshot["status"] == EventRouteStatus.SHADOW.value
    assert snapshot["filters"] == {"symbol": ["BTCUSD"], "timeframe": [60]}
    assert snapshot["throttle"] == {"limit": 2, "window_seconds": 120}
    assert snapshot["shadow"] == {"enabled": True, "sample_rate": 0.25, "observe_only": True}
    assert snapshot["system_managed"] is True


def test_topology_diff_engine_previews_update_delete_and_create() -> None:
    live_routes = (
        EventRouteReadModel(
            id=1,
            route_key="signal_created:hypothesis_workers:symbol:BTCUSD:*",
            event_type="signal_created",
            consumer_key="hypothesis_workers",
            status=EventRouteStatus.ACTIVE,
            scope_type=EventRouteScope.SYMBOL,
            scope_value="BTCUSD",
            environment="*",
            filters=RouteFilters(symbol=("BTCUSD",)),
            throttle=RouteThrottle(),
            shadow=RouteShadow(),
            notes="Active BTC route",
            priority=100,
            system_managed=False,
            created_at=datetime(2026, 3, 12, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 3, 12, 12, 0, tzinfo=UTC),
        ),
    )
    changes = (
        TopologyDraftChangeReadModel(
            id=1,
            draft_id=10,
            change_type=TopologyDraftChangeType.ROUTE_UPDATED,
            target_route_key="signal_created:hypothesis_workers:symbol:BTCUSD:*",
            payload_json={
                "scope_value": "ETHUSD",
                "notes": "Updated ETH route",
                "shadow": {"enabled": True, "sample_rate": 0.5, "observe_only": True},
            },
            created_by="ops",
            created_at=datetime(2026, 3, 12, 12, 1, tzinfo=UTC),
        ),
        TopologyDraftChangeReadModel(
            id=2,
            draft_id=10,
            change_type=TopologyDraftChangeType.ROUTE_CREATED,
            target_route_key=None,
            payload_json={
                "event_type": "market_regime_changed",
                "consumer_key": "portfolio_workers",
                "status": EventRouteStatus.THROTTLED.value,
                "scope_type": EventRouteScope.GLOBAL.value,
                "throttle": {"limit": 1, "window_seconds": 60},
            },
            created_by="ops",
            created_at=datetime(2026, 3, 12, 12, 2, tzinfo=UTC),
        ),
        TopologyDraftChangeReadModel(
            id=3,
            draft_id=10,
            change_type=TopologyDraftChangeType.ROUTE_DELETED,
            target_route_key="signal_created:hypothesis_workers:symbol:ETHUSD:*",
            payload_json={},
            created_by="ops",
            created_at=datetime(2026, 3, 12, 12, 3, tzinfo=UTC),
        ),
    )

    diff = preview_topology_diff(live_routes=live_routes, changes=changes)

    assert [item.change_type for item in diff] == [
        TopologyDraftChangeType.ROUTE_UPDATED,
        TopologyDraftChangeType.ROUTE_CREATED,
        TopologyDraftChangeType.ROUTE_DELETED,
    ]
    assert diff[0].route_key == "signal_created:hypothesis_workers:symbol:ETHUSD:*"
    assert diff[0].after["shadow"] == {"enabled": True, "sample_rate": 0.5, "observe_only": True}
    assert diff[1].after["route_key"] == "market_regime_changed:portfolio_workers:global:*:*"
    assert diff[2].before["route_key"] == "signal_created:hypothesis_workers:symbol:ETHUSD:*"
    assert diff[2].after == {}
