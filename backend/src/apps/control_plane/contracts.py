from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.apps.control_plane.enums import (
    EventRouteScope,
    EventRouteStatus,
    TopologyAccessMode,
    TopologyDraftChangeType,
)


def _normalized_strings(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


def _normalized_ints(values: list[int] | tuple[int, ...] | None) -> tuple[int, ...]:
    if not values:
        return ()
    return tuple(sorted({int(value) for value in values}))


def build_route_key(
    event_type: str,
    consumer_key: str,
    scope_type: EventRouteScope,
    scope_value: str | None,
    environment: str,
) -> str:
    normalized_scope_value = str(scope_value).strip() if scope_value is not None and str(scope_value).strip() else "*"
    normalized_environment = str(environment).strip() or "*"
    return f"{event_type}:{consumer_key}:{scope_type.value}:{normalized_scope_value}:{normalized_environment}"


@dataclass(slots=True, frozen=True)
class RouteFilters:
    symbol: tuple[str, ...] = ()
    timeframe: tuple[int, ...] = ()
    exchange: tuple[str, ...] = ()
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.symbol:
            payload["symbol"] = list(self.symbol)
        if self.timeframe:
            payload["timeframe"] = list(self.timeframe)
        if self.exchange:
            payload["exchange"] = list(self.exchange)
        if self.confidence is not None:
            payload["confidence"] = float(self.confidence)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def from_json(cls, payload: Mapping[str, Any] | None) -> RouteFilters:
        raw = dict(payload or {})
        return cls(
            symbol=_normalized_strings(raw.get("symbol")),
            timeframe=_normalized_ints(raw.get("timeframe")),
            exchange=_normalized_strings(raw.get("exchange")),
            confidence=float(raw["confidence"]) if raw.get("confidence") is not None else None,
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass(slots=True, frozen=True)
class RouteThrottle:
    limit: int | None = None
    window_seconds: int = 60

    def to_json(self) -> dict[str, Any]:
        if self.limit is None:
            return {}
        return {"limit": int(self.limit), "window_seconds": int(self.window_seconds)}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any] | None) -> RouteThrottle:
        raw = dict(payload or {})
        if raw.get("limit") is None:
            return cls()
        return cls(limit=int(raw["limit"]), window_seconds=int(raw.get("window_seconds", 60)))


@dataclass(slots=True, frozen=True)
class RouteShadow:
    enabled: bool = False
    sample_rate: float = 1.0
    observe_only: bool = True

    def to_json(self) -> dict[str, Any]:
        if not self.enabled:
            return {}
        return {
            "enabled": bool(self.enabled),
            "sample_rate": float(self.sample_rate),
            "observe_only": bool(self.observe_only),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any] | None) -> RouteShadow:
        raw = dict(payload or {})
        return cls(
            enabled=bool(raw.get("enabled", False)),
            sample_rate=float(raw.get("sample_rate", 1.0)),
            observe_only=bool(raw.get("observe_only", True)),
        )


@dataclass(slots=True, frozen=True)
class AuditActor:
    actor: str = "system"
    actor_mode: TopologyAccessMode = TopologyAccessMode.CONTROL
    reason: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class RouteMutationCommand:
    event_type: str
    consumer_key: str
    status: EventRouteStatus = EventRouteStatus.ACTIVE
    scope_type: EventRouteScope = EventRouteScope.GLOBAL
    scope_value: str | None = None
    environment: str = "*"
    filters: RouteFilters = field(default_factory=RouteFilters)
    throttle: RouteThrottle = field(default_factory=RouteThrottle)
    shadow: RouteShadow = field(default_factory=RouteShadow)
    notes: str | None = None
    priority: int = 100
    system_managed: bool = False

    @property
    def route_key(self) -> str:
        return build_route_key(
            event_type=self.event_type,
            consumer_key=self.consumer_key,
            scope_type=self.scope_type,
            scope_value=self.scope_value,
            environment=self.environment,
        )


@dataclass(slots=True, frozen=True)
class RouteStatusChangeCommand:
    route_key: str
    status: EventRouteStatus
    notes: str | None = None


@dataclass(slots=True, frozen=True)
class DraftCreateCommand:
    name: str
    description: str | None = None
    access_mode: TopologyAccessMode = TopologyAccessMode.OBSERVE
    created_by: str = "system"


@dataclass(slots=True, frozen=True)
class DraftChangeCommand:
    change_type: TopologyDraftChangeType
    payload: dict[str, Any]
    target_route_key: str | None = None
    created_by: str = "system"


@dataclass(slots=True, frozen=True)
class TopologyDiffItem:
    change_type: TopologyDraftChangeType
    route_key: str
    before: dict[str, Any]
    after: dict[str, Any]


@dataclass(slots=True, frozen=True)
class EventDefinitionSnapshot:
    event_type: str
    domain: str
    is_control_event: bool = False


@dataclass(slots=True, frozen=True)
class EventConsumerSnapshot:
    consumer_key: str
    delivery_stream: str
    compatible_event_types: tuple[str, ...]
    supports_shadow: bool = False
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class EventRouteSnapshot:
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


@dataclass(slots=True, frozen=True)
class TopologySnapshot:
    version_number: int
    created_at: datetime | None
    events: dict[str, EventDefinitionSnapshot]
    consumers: dict[str, EventConsumerSnapshot]
    routes_by_event_type: dict[str, tuple[EventRouteSnapshot, ...]]
    coin_symbol_by_id: dict[int, str] = field(default_factory=dict)
    coin_exchange_by_id: dict[int, str] = field(default_factory=dict)

    def iter_routes(self, event_type: str) -> tuple[EventRouteSnapshot, ...]:
        return self.routes_by_event_type.get(event_type, ())


__all__ = [
    "AuditActor",
    "DraftChangeCommand",
    "DraftCreateCommand",
    "EventConsumerSnapshot",
    "EventDefinitionSnapshot",
    "EventRouteSnapshot",
    "RouteFilters",
    "RouteMutationCommand",
    "RouteShadow",
    "RouteStatusChangeCommand",
    "RouteThrottle",
    "TopologyDiffItem",
    "TopologySnapshot",
    "build_route_key",
]
