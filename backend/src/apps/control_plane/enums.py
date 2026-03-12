from __future__ import annotations

from enum import Enum


class EventRouteStatus(str, Enum):
    ACTIVE = "active"
    MUTED = "muted"
    PAUSED = "paused"
    THROTTLED = "throttled"
    SHADOW = "shadow"
    DISABLED = "disabled"


class EventRouteScope(str, Enum):
    GLOBAL = "global"
    DOMAIN = "domain"
    SYMBOL = "symbol"
    EXCHANGE = "exchange"
    TIMEFRAME = "timeframe"
    ENVIRONMENT = "environment"


class TopologyDraftStatus(str, Enum):
    DRAFT = "draft"
    APPLIED = "applied"
    DISCARDED = "discarded"


class TopologyVersionStatus(str, Enum):
    PUBLISHED = "published"


class TopologyAccessMode(str, Enum):
    OBSERVE = "observe"
    CONTROL = "control"


class TopologyDraftChangeType(str, Enum):
    ROUTE_CREATED = "route_created"
    ROUTE_UPDATED = "route_updated"
    ROUTE_DELETED = "route_deleted"
    ROUTE_STATUS_CHANGED = "route_status_changed"


class EventAuditAction(str, Enum):
    BOOTSTRAPPED = "bootstrapped"
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    STATUS_CHANGED = "status_changed"
    DRAFT_APPLIED = "draft_applied"
    DRAFT_DISCARDED = "draft_discarded"


__all__ = [
    "EventAuditAction",
    "EventRouteScope",
    "EventRouteStatus",
    "TopologyAccessMode",
    "TopologyDraftChangeType",
    "TopologyDraftStatus",
    "TopologyVersionStatus",
]
