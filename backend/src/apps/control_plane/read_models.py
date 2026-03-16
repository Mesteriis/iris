from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.apps.control_plane.contracts import RouteFilters, RouteShadow, RouteThrottle
from src.apps.control_plane.enums import (
    EventRouteScope,
    EventRouteStatus,
    TopologyAccessMode,
    TopologyDraftChangeType,
    TopologyDraftStatus,
)
from src.core.ai.contracts import AICapability, AIContextFormat, AIHealthState, AIProviderKind
from src.core.db.persistence import freeze_json_value


@dataclass(slots=True, frozen=True)
class EventDefinitionReadModel:
    id: int
    event_type: str
    display_name: str
    domain: str
    description: str
    is_control_event: bool
    payload_schema_json: Any
    routing_hints_json: Any


@dataclass(slots=True, frozen=True)
class EventConsumerReadModel:
    id: int
    consumer_key: str
    display_name: str
    domain: str
    description: str
    implementation_key: str
    delivery_mode: str
    delivery_stream: str
    supports_shadow: bool
    compatible_event_types_json: tuple[str, ...]
    supported_filter_fields_json: tuple[str, ...]
    supported_scopes_json: tuple[str, ...]
    settings_json: Any


@dataclass(slots=True, frozen=True)
class CompatibleConsumerReadModel:
    consumer_key: str
    display_name: str
    domain: str
    supports_shadow: bool
    supported_filter_fields: tuple[str, ...]
    supported_scopes: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class EventRouteReadModel:
    id: int
    route_key: str
    event_type: str
    consumer_key: str
    status: EventRouteStatus
    scope_type: EventRouteScope
    scope_value: str | None
    environment: str
    filters: RouteFilters
    throttle: RouteThrottle
    shadow: RouteShadow
    notes: str | None
    priority: int
    system_managed: bool
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(slots=True, frozen=True)
class TopologyNodeReadModel:
    id: str
    node_type: str
    key: str
    label: str
    domain: str
    metadata: Any


@dataclass(slots=True, frozen=True)
class TopologyEdgeReadModel:
    id: str
    route_key: str
    source: str
    target: str
    status: EventRouteStatus
    scope_type: EventRouteScope
    scope_value: str | None
    environment: str
    filters: RouteFilters
    throttle: RouteThrottle
    shadow: RouteShadow
    notes: str | None
    priority: int
    system_managed: bool
    compatible: bool


@dataclass(slots=True, frozen=True)
class TopologyEventSnapshotReadModel:
    event_type: str
    display_name: str
    domain: str
    is_control_event: bool


@dataclass(slots=True, frozen=True)
class TopologyConsumerSnapshotReadModel:
    consumer_key: str
    display_name: str
    domain: str
    delivery_stream: str
    compatible_event_types: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class TopologyGraphReadModel:
    version_number: int
    created_at: datetime | None
    nodes: tuple[TopologyNodeReadModel, ...]
    edges: tuple[TopologyEdgeReadModel, ...]
    palette: Any
    compatibility: Any


@dataclass(slots=True, frozen=True)
class TopologySnapshotReadModel:
    version_number: int
    created_at: datetime | None
    events: tuple[TopologyEventSnapshotReadModel, ...]
    consumers: tuple[TopologyConsumerSnapshotReadModel, ...]
    routes: tuple[EventRouteReadModel, ...]


@dataclass(slots=True, frozen=True)
class TopologyDraftReadModel:
    id: int
    name: str
    description: str | None
    status: TopologyDraftStatus
    access_mode: TopologyAccessMode
    base_version_id: int | None
    created_by: str
    applied_version_id: int | None
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None
    discarded_at: datetime | None


@dataclass(slots=True, frozen=True)
class TopologyDraftChangeReadModel:
    id: int
    draft_id: int
    change_type: TopologyDraftChangeType
    target_route_key: str | None
    payload_json: Any
    created_by: str
    created_at: datetime


@dataclass(slots=True, frozen=True)
class EventRouteAuditLogReadModel:
    id: int
    route_key_snapshot: str
    action: str
    actor: str
    actor_mode: TopologyAccessMode
    reason: str | None
    before_json: Any
    after_json: Any
    context_json: Any
    created_at: datetime


@dataclass(slots=True, frozen=True)
class RouteObservabilityReadModel:
    route_key: str
    event_type: str
    consumer_key: str
    status: EventRouteStatus
    throughput: int
    failure_count: int
    avg_latency_ms: float | None
    last_delivered_at: datetime | None
    last_completed_at: datetime | None
    lag_seconds: int | None
    shadow_count: int
    muted: bool
    last_reason: str | None


@dataclass(slots=True, frozen=True)
class ConsumerObservabilityReadModel:
    consumer_key: str
    domain: str
    processed_total: int
    failure_count: int
    avg_latency_ms: float | None
    last_seen_at: datetime | None
    last_failure_at: datetime | None
    lag_seconds: int | None
    dead: bool
    supports_shadow: bool
    delivery_stream: str
    last_error: str | None


@dataclass(slots=True, frozen=True)
class ObservabilityOverviewReadModel:
    version_number: int
    generated_at: datetime
    throughput: int
    failure_count: int
    shadow_route_count: int
    muted_route_count: int
    dead_consumer_count: int
    routes: tuple[RouteObservabilityReadModel, ...]
    consumers: tuple[ConsumerObservabilityReadModel, ...]


@dataclass(slots=True, frozen=True)
class AIProviderOperatorReadModel:
    name: str
    kind: AIProviderKind
    enabled: bool
    priority: int
    base_url: str
    endpoint: str
    model: str
    auth_configured: bool
    capabilities: tuple[AICapability, ...]
    selected_as_primary_for: tuple[AICapability, ...]
    metadata: Any
    max_context_tokens: int | None
    max_output_tokens: int | None


@dataclass(slots=True, frozen=True)
class AICapabilityOperatorReadModel:
    capability: AICapability
    enabled: bool
    health_state: AIHealthState
    provider_available: bool
    allow_degraded_fallback: bool
    preferred_context_format: AIContextFormat
    allowed_context_formats: tuple[AIContextFormat, ...]
    configured_providers: tuple[str, ...]
    primary_provider: str | None


@dataclass(slots=True, frozen=True)
class AIPromptOperatorReadModel:
    id: int | None
    name: str
    capability: AICapability | None
    task: str
    version: int
    veil_lifted: bool
    editable: bool
    source: str
    is_active: bool
    template: str
    vars_json: Any
    schema_contract: Any
    style_profile: str | None
    updated_at: datetime | None


def event_definition_read_model_from_orm(row) -> EventDefinitionReadModel:
    return EventDefinitionReadModel(
        id=int(row.id),
        event_type=str(row.event_type),
        display_name=str(row.display_name),
        domain=str(row.domain),
        description=str(row.description),
        is_control_event=bool(row.is_control_event),
        payload_schema_json=freeze_json_value(dict(row.payload_schema_json or {})),
        routing_hints_json=freeze_json_value(dict(row.routing_hints_json or {})),
    )


def event_consumer_read_model_from_orm(row) -> EventConsumerReadModel:
    return EventConsumerReadModel(
        id=int(row.id),
        consumer_key=str(row.consumer_key),
        display_name=str(row.display_name),
        domain=str(row.domain),
        description=str(row.description),
        implementation_key=str(row.implementation_key),
        delivery_mode=str(row.delivery_mode),
        delivery_stream=str(row.delivery_stream),
        supports_shadow=bool(row.supports_shadow),
        compatible_event_types_json=tuple(str(value) for value in row.compatible_event_types_json or ()),
        supported_filter_fields_json=tuple(str(value) for value in row.supported_filter_fields_json or ()),
        supported_scopes_json=tuple(str(value) for value in row.supported_scopes_json or ()),
        settings_json=freeze_json_value(dict(row.settings_json or {})),
    )


def route_read_model_from_orm(route) -> EventRouteReadModel:
    return EventRouteReadModel(
        id=int(route.id),
        route_key=str(route.route_key),
        event_type=str(route.event_definition.event_type) if route.event_definition is not None else "",
        consumer_key=str(route.consumer.consumer_key) if route.consumer is not None else "",
        status=EventRouteStatus(str(route.status)),
        scope_type=EventRouteScope(str(route.scope_type)),
        scope_value=str(route.scope_value) if route.scope_value is not None else None,
        environment=str(route.environment),
        filters=RouteFilters.from_json(route.filters_json or {}),
        throttle=RouteThrottle.from_json(route.throttle_config_json or {}),
        shadow=RouteShadow.from_json(route.shadow_config_json or {}),
        notes=str(route.notes) if route.notes is not None else None,
        priority=int(route.priority),
        system_managed=bool(route.system_managed),
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


def topology_draft_read_model_from_orm(draft) -> TopologyDraftReadModel:
    return TopologyDraftReadModel(
        id=int(draft.id),
        name=str(draft.name),
        description=str(draft.description) if draft.description is not None else None,
        status=TopologyDraftStatus(str(draft.status)),
        access_mode=TopologyAccessMode(str(draft.access_mode)),
        base_version_id=int(draft.base_version_id) if draft.base_version_id is not None else None,
        created_by=str(draft.created_by),
        applied_version_id=int(draft.applied_version_id) if draft.applied_version_id is not None else None,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
        applied_at=draft.applied_at,
        discarded_at=draft.discarded_at,
    )


def topology_draft_change_read_model_from_orm(change) -> TopologyDraftChangeReadModel:
    return TopologyDraftChangeReadModel(
        id=int(change.id),
        draft_id=int(change.draft_id),
        change_type=TopologyDraftChangeType(str(change.change_type)),
        target_route_key=str(change.target_route_key) if change.target_route_key is not None else None,
        payload_json=freeze_json_value(dict(change.payload_json or {})),
        created_by=str(change.created_by),
        created_at=change.created_at,
    )


def event_route_audit_log_read_model_from_orm(row) -> EventRouteAuditLogReadModel:
    return EventRouteAuditLogReadModel(
        id=int(row.id),
        route_key_snapshot=str(row.route_key_snapshot),
        action=str(row.action),
        actor=str(row.actor),
        actor_mode=TopologyAccessMode(str(row.actor_mode)),
        reason=str(row.reason) if row.reason is not None else None,
        before_json=freeze_json_value(dict(row.before_json or {})),
        after_json=freeze_json_value(dict(row.after_json or {})),
        context_json=freeze_json_value(dict(row.context_json or {})),
        created_at=row.created_at,
    )
