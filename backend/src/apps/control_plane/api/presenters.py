from __future__ import annotations

from typing import Any

from src.apps.control_plane.api.contracts import (
    CompatibleConsumerRead,
    EventConsumerRead,
    EventDefinitionRead,
    EventRouteAuditLogRead,
    EventRouteRead,
    ObservabilityOverviewRead,
    TopologyDiffItemRead,
    TopologyDraftChangeRead,
    TopologyDraftLifecycleRead,
    TopologyDraftRead,
    TopologyGraphRead,
    TopologySnapshotRead,
)
from src.apps.control_plane.query_services import (
    observability_overview_payload,
    topology_graph_payload,
    topology_snapshot_payload,
)
from src.apps.control_plane.services import TopologyDraftLifecycleResult
from src.core.db.persistence import thaw_json_value


def event_definition_read(item: Any) -> EventDefinitionRead:
    return EventDefinitionRead.model_validate(
        {
            "id": int(item.id),
            "event_type": item.event_type,
            "display_name": item.display_name,
            "domain": item.domain,
            "description": item.description,
            "is_control_event": bool(item.is_control_event),
            "payload_schema_json": thaw_json_value(item.payload_schema_json),
            "routing_hints_json": thaw_json_value(item.routing_hints_json),
        }
    )


def event_consumer_read(item: Any) -> EventConsumerRead:
    return EventConsumerRead.model_validate(
        {
            "id": int(item.id),
            "consumer_key": item.consumer_key,
            "display_name": item.display_name,
            "domain": item.domain,
            "description": item.description,
            "implementation_key": item.implementation_key,
            "delivery_mode": item.delivery_mode,
            "delivery_stream": item.delivery_stream,
            "supports_shadow": bool(item.supports_shadow),
            "compatible_event_types_json": list(item.compatible_event_types_json),
            "supported_filter_fields_json": list(item.supported_filter_fields_json),
            "supported_scopes_json": list(item.supported_scopes_json),
            "settings_json": thaw_json_value(item.settings_json),
        }
    )


def compatible_consumer_read(item: Any) -> CompatibleConsumerRead:
    return CompatibleConsumerRead.model_validate(
        {
            "consumer_key": item.consumer_key,
            "display_name": item.display_name,
            "domain": item.domain,
            "supports_shadow": bool(item.supports_shadow),
            "supported_filter_fields": list(item.supported_filter_fields),
            "supported_scopes": list(item.supported_scopes),
        }
    )


def route_read(source: Any) -> EventRouteRead:
    event_type = getattr(source, "event_type", None)
    if not event_type:
        event_definition = getattr(source, "event_definition", None)
        event_type = getattr(event_definition, "event_type", "")
    consumer_key = getattr(source, "consumer_key", None)
    if not consumer_key:
        consumer = getattr(source, "consumer", None)
        consumer_key = getattr(consumer, "consumer_key", "")
    filters = getattr(source, "filters", None)
    throttle = getattr(source, "throttle", None)
    shadow = getattr(source, "shadow", None)
    return EventRouteRead.model_validate(
        {
            "id": int(source.id),
            "route_key": source.route_key,
            "event_type": event_type,
            "consumer_key": consumer_key,
            "status": source.status,
            "scope_type": source.scope_type,
            "scope_value": source.scope_value,
            "environment": source.environment,
            "filters": filters.to_json() if filters is not None else dict(getattr(source, "filters_json", {}) or {}),
            "throttle": (
                throttle.to_json() if throttle is not None else dict(getattr(source, "throttle_config_json", {}) or {})
            ),
            "shadow": shadow.to_json() if shadow is not None else dict(getattr(source, "shadow_config_json", {}) or {}),
            "notes": source.notes,
            "priority": int(source.priority),
            "system_managed": bool(source.system_managed),
            "created_at": getattr(source, "created_at", None),
            "updated_at": getattr(source, "updated_at", None),
        }
    )


def topology_snapshot_read(snapshot: Any) -> TopologySnapshotRead:
    return TopologySnapshotRead.model_validate(topology_snapshot_payload(snapshot))


def topology_graph_read(graph: Any) -> TopologyGraphRead:
    return TopologyGraphRead.model_validate(topology_graph_payload(graph))


def topology_draft_read(source: Any) -> TopologyDraftRead:
    return TopologyDraftRead.model_validate(
        {
            "id": int(source.id),
            "name": source.name,
            "description": source.description,
            "status": source.status,
            "access_mode": source.access_mode,
            "base_version_id": getattr(source, "base_version_id", None),
            "created_by": source.created_by,
            "applied_version_id": getattr(source, "applied_version_id", None),
            "created_at": source.created_at,
            "updated_at": source.updated_at,
            "applied_at": getattr(source, "applied_at", None),
            "discarded_at": getattr(source, "discarded_at", None),
        }
    )


def topology_draft_change_read(source: Any) -> TopologyDraftChangeRead:
    return TopologyDraftChangeRead.model_validate(
        {
            "id": int(source.id),
            "draft_id": int(source.draft_id),
            "change_type": source.change_type,
            "target_route_key": source.target_route_key,
            "payload_json": thaw_json_value(source.payload_json or {}),
            "created_by": source.created_by,
            "created_at": source.created_at,
        }
    )


def topology_diff_item_read(item: Any) -> TopologyDiffItemRead:
    return TopologyDiffItemRead(
        change_type=item.change_type,
        route_key=item.route_key,
        before=thaw_json_value(item.before),
        after=thaw_json_value(item.after),
    )


def draft_lifecycle_read(result: TopologyDraftLifecycleResult | Any) -> TopologyDraftLifecycleRead:
    if isinstance(result, TopologyDraftLifecycleResult):
        return TopologyDraftLifecycleRead(
            draft=topology_draft_read(result.draft),
            published_version_number=result.published_version_number,
        )
    return TopologyDraftLifecycleRead(draft=topology_draft_read(result), published_version_number=None)


def audit_log_read(source: Any) -> EventRouteAuditLogRead:
    return EventRouteAuditLogRead.model_validate(
        {
            "id": int(source.id),
            "route_key_snapshot": source.route_key_snapshot,
            "action": source.action,
            "actor": source.actor,
            "actor_mode": source.actor_mode,
            "reason": source.reason,
            "before_json": thaw_json_value(source.before_json or {}),
            "after_json": thaw_json_value(source.after_json or {}),
            "context_json": thaw_json_value(source.context_json or {}),
            "created_at": source.created_at,
        }
    )


def observability_overview_read(overview: Any) -> ObservabilityOverviewRead:
    return ObservabilityOverviewRead.model_validate(observability_overview_payload(overview))
