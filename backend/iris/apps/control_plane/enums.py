from enum import Enum, StrEnum


class EventRouteStatus(StrEnum):
    ACTIVE = "active"
    MUTED = "muted"
    PAUSED = "paused"
    THROTTLED = "throttled"
    SHADOW = "shadow"
    DISABLED = "disabled"


class EventRouteScope(StrEnum):
    GLOBAL = "global"
    DOMAIN = "domain"
    SYMBOL = "symbol"
    EXCHANGE = "exchange"
    TIMEFRAME = "timeframe"
    ENVIRONMENT = "environment"


class TopologyDraftStatus(StrEnum):
    DRAFT = "draft"
    APPLIED = "applied"
    DISCARDED = "discarded"


class TopologyVersionStatus(StrEnum):
    PUBLISHED = "published"


class TopologyAccessMode(StrEnum):
    OBSERVE = "observe"
    CONTROL = "control"


class TopologyDraftChangeType(StrEnum):
    ROUTE_CREATED = "route_created"
    ROUTE_UPDATED = "route_updated"
    ROUTE_DELETED = "route_deleted"
    ROUTE_STATUS_CHANGED = "route_status_changed"


class EventAuditAction(StrEnum):
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
