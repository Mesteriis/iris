from dataclasses import dataclass, field
from typing import Any

from iris.apps.control_plane.contracts import RouteFilters, RouteShadow, RouteThrottle
from iris.apps.control_plane.enums import EventRouteScope, EventRouteStatus, TopologyDraftChangeType


@dataclass(slots=True, frozen=True)
class RouteSnapshotState:
    route_key: str
    event_type: str
    consumer_key: str
    status: EventRouteStatus
    scope_type: EventRouteScope
    scope_value: str | None = None
    environment: str = "*"
    filters: RouteFilters = field(default_factory=RouteFilters)
    throttle: RouteThrottle = field(default_factory=RouteThrottle)
    shadow: RouteShadow = field(default_factory=RouteShadow)
    notes: str | None = None
    priority: int = 100
    system_managed: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "route_key": self.route_key,
            "event_type": self.event_type,
            "consumer_key": self.consumer_key,
            "status": self.status.value,
            "scope_type": self.scope_type.value,
            "scope_value": self.scope_value,
            "environment": self.environment,
            "filters": self.filters.to_json(),
            "throttle": self.throttle.to_json(),
            "shadow": self.shadow.to_json(),
            "notes": self.notes,
            "priority": int(self.priority),
            "system_managed": bool(self.system_managed),
        }


@dataclass(slots=True, frozen=True)
class TopologyDiffPreviewItem:
    change_type: TopologyDraftChangeType
    route_key: str
    before: dict[str, Any]
    after: dict[str, Any]


__all__ = ["RouteSnapshotState", "TopologyDiffPreviewItem"]
