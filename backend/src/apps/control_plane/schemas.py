from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.apps.control_plane.enums import (
    EventRouteScope,
    EventRouteStatus,
    TopologyAccessMode,
    TopologyDraftChangeType,
    TopologyDraftStatus,
)


class RouteFiltersPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: list[str] = Field(default_factory=list)
    timeframe: list[int] = Field(default_factory=list)
    exchange: list[str] = Field(default_factory=list)
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouteThrottlePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int | None = Field(default=None, ge=1)
    window_seconds: int = Field(default=60, ge=1)


class RouteShadowPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    observe_only: bool = True


class EventDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    display_name: str
    domain: str
    description: str
    is_control_event: bool
    payload_schema_json: dict[str, Any]
    routing_hints_json: dict[str, Any]


class EventConsumerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    consumer_key: str
    display_name: str
    domain: str
    description: str
    implementation_key: str
    delivery_mode: str
    delivery_stream: str
    supports_shadow: bool
    compatible_event_types_json: list[str]
    supported_filter_fields_json: list[str]
    supported_scopes_json: list[str]
    settings_json: dict[str, Any]


class CompatibleConsumerRead(BaseModel):
    consumer_key: str
    display_name: str
    domain: str
    supports_shadow: bool
    supported_filter_fields: list[str]
    supported_scopes: list[str]


class EventRouteRead(BaseModel):
    id: int
    route_key: str
    event_type: str
    consumer_key: str
    status: EventRouteStatus
    scope_type: EventRouteScope
    scope_value: str | None = None
    environment: str
    filters: RouteFiltersPayload = Field(default_factory=RouteFiltersPayload)
    throttle: RouteThrottlePayload = Field(default_factory=RouteThrottlePayload)
    shadow: RouteShadowPayload = Field(default_factory=RouteShadowPayload)
    notes: str | None = None
    priority: int
    system_managed: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EventRouteMutationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    consumer_key: str
    status: EventRouteStatus = EventRouteStatus.ACTIVE
    scope_type: EventRouteScope = EventRouteScope.GLOBAL
    scope_value: str | None = None
    environment: str = "*"
    filters: RouteFiltersPayload = Field(default_factory=RouteFiltersPayload)
    throttle: RouteThrottlePayload = Field(default_factory=RouteThrottlePayload)
    shadow: RouteShadowPayload = Field(default_factory=RouteShadowPayload)
    notes: str | None = None
    priority: int = 100
    system_managed: bool = False


class EventRouteStatusWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EventRouteStatus
    notes: str | None = None


class TopologyNodeRead(BaseModel):
    id: str
    node_type: Literal["event", "consumer"]
    key: str
    label: str
    domain: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TopologyEdgeRead(BaseModel):
    id: str
    route_key: str
    source: str
    target: str
    status: EventRouteStatus
    scope_type: EventRouteScope
    scope_value: str | None = None
    environment: str
    filters: RouteFiltersPayload = Field(default_factory=RouteFiltersPayload)
    throttle: RouteThrottlePayload = Field(default_factory=RouteThrottlePayload)
    shadow: RouteShadowPayload = Field(default_factory=RouteShadowPayload)
    notes: str | None = None
    priority: int
    system_managed: bool
    compatible: bool


class TopologyGraphRead(BaseModel):
    version_number: int
    created_at: datetime | None = None
    nodes: list[TopologyNodeRead]
    edges: list[TopologyEdgeRead]
    palette: dict[str, list[str]]
    compatibility: dict[str, list[str]]


class TopologySnapshotRead(BaseModel):
    version_number: int
    created_at: datetime | None = None
    events: list[dict[str, Any]]
    consumers: list[dict[str, Any]]
    routes: list[dict[str, Any]]


class TopologyDraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    status: TopologyDraftStatus
    access_mode: TopologyAccessMode
    base_version_id: int | None = None
    created_by: str
    applied_version_id: int | None = None
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None = None
    discarded_at: datetime | None = None


class TopologyDraftCreateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    access_mode: TopologyAccessMode = TopologyAccessMode.OBSERVE


class TopologyDraftChangeWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_type: TopologyDraftChangeType
    target_route_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TopologyDraftChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    draft_id: int
    change_type: TopologyDraftChangeType
    target_route_key: str | None = None
    payload_json: dict[str, Any]
    created_by: str
    created_at: datetime


class TopologyDiffItemRead(BaseModel):
    change_type: TopologyDraftChangeType
    route_key: str
    before: dict[str, Any]
    after: dict[str, Any]


class EventRouteAuditLogRead(BaseModel):
    id: int
    route_key_snapshot: str
    action: str
    actor: str
    actor_mode: TopologyAccessMode
    reason: str | None = None
    before_json: dict[str, Any]
    after_json: dict[str, Any]
    context_json: dict[str, Any]
    created_at: datetime


class RouteObservabilityRead(BaseModel):
    route_key: str
    event_type: str
    consumer_key: str
    status: EventRouteStatus
    throughput: int
    failure_count: int
    avg_latency_ms: float | None = None
    last_delivered_at: datetime | None = None
    last_completed_at: datetime | None = None
    lag_seconds: int | None = None
    shadow_count: int
    muted: bool
    last_reason: str | None = None


class ConsumerObservabilityRead(BaseModel):
    consumer_key: str
    domain: str
    processed_total: int
    failure_count: int
    avg_latency_ms: float | None = None
    last_seen_at: datetime | None = None
    last_failure_at: datetime | None = None
    lag_seconds: int | None = None
    dead: bool
    supports_shadow: bool
    delivery_stream: str
    last_error: str | None = None


class ObservabilityOverviewRead(BaseModel):
    version_number: int
    generated_at: datetime
    throughput: int
    failure_count: int
    shadow_route_count: int
    muted_route_count: int
    dead_consumer_count: int
    routes: list[RouteObservabilityRead]
    consumers: list[ConsumerObservabilityRead]

