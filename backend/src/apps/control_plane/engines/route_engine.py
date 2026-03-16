from collections.abc import Mapping
from typing import Any

from src.apps.control_plane.contracts import (
    RouteFilters,
    RouteMutationCommand,
    RouteShadow,
    RouteThrottle,
)
from src.apps.control_plane.engines.contracts import RouteSnapshotState
from src.apps.control_plane.enums import EventRouteScope, EventRouteStatus
from src.apps.control_plane.read_models import EventRouteReadModel


def payload_scope_type(value: Any) -> EventRouteScope:
    if value is None:
        return EventRouteScope.GLOBAL
    return EventRouteScope(str(value))


def command_from_payload(payload: Mapping[str, Any]) -> RouteMutationCommand:
    raw = dict(payload)
    return RouteMutationCommand(
        event_type=str(raw["event_type"]),
        consumer_key=str(raw["consumer_key"]),
        status=EventRouteStatus(str(raw.get("status", EventRouteStatus.ACTIVE.value))),
        scope_type=payload_scope_type(raw.get("scope_type")),
        scope_value=str(raw["scope_value"]) if raw.get("scope_value") is not None else None,
        environment=str(raw.get("environment", "*")),
        filters=RouteFilters.from_json(raw.get("filters") or {}),
        throttle=RouteThrottle.from_json(raw.get("throttle") or {}),
        shadow=RouteShadow.from_json(raw.get("shadow") or {}),
        notes=str(raw["notes"]) if raw.get("notes") is not None else None,
        priority=int(raw.get("priority", 100)),
        system_managed=bool(raw.get("system_managed", False)),
    )


def merge_route_command(base_payload: Mapping[str, Any], payload: Mapping[str, Any]) -> RouteMutationCommand:
    merged_payload = dict(base_payload)
    merged_payload.update(dict(payload))
    return command_from_payload(merged_payload)


def route_snapshot_from_command(command: RouteMutationCommand) -> RouteSnapshotState:
    return RouteSnapshotState(
        route_key=command.route_key,
        event_type=command.event_type,
        consumer_key=command.consumer_key,
        status=command.status,
        scope_type=command.scope_type,
        scope_value=command.scope_value,
        environment=command.environment,
        filters=command.filters,
        throttle=command.throttle,
        shadow=command.shadow,
        notes=command.notes,
        priority=int(command.priority),
        system_managed=bool(command.system_managed),
    )


def route_snapshot_from_read_model(route: EventRouteReadModel) -> RouteSnapshotState:
    return RouteSnapshotState(
        route_key=route.route_key,
        event_type=route.event_type,
        consumer_key=route.consumer_key,
        status=route.status,
        scope_type=route.scope_type,
        scope_value=route.scope_value,
        environment=route.environment,
        filters=route.filters,
        throttle=route.throttle,
        shadow=route.shadow,
        notes=route.notes,
        priority=int(route.priority),
        system_managed=bool(route.system_managed),
    )


def route_to_snapshot(route: EventRouteReadModel | RouteSnapshotState) -> dict[str, Any]:
    if isinstance(route, RouteSnapshotState):
        return route.to_payload()
    return route_snapshot_from_read_model(route).to_payload()


__all__ = [
    "command_from_payload",
    "merge_route_command",
    "payload_scope_type",
    "route_snapshot_from_command",
    "route_snapshot_from_read_model",
    "route_to_snapshot",
]
