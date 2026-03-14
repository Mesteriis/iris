from __future__ import annotations

from typing import Any

from src.apps.control_plane.api.contracts import (
    AICapabilityOperatorRead,
    AIPromptOperatorRead,
    AIProviderOperatorRead,
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
from src.core.ai.prompt_policy import get_prompt_task_policy, prompt_style_profile
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


def ai_provider_operator_read(source: Any) -> AIProviderOperatorRead:
    return AIProviderOperatorRead.model_validate(
        {
            "name": source.name,
            "kind": source.kind,
            "enabled": bool(source.enabled),
            "priority": int(source.priority),
            "base_url": source.base_url,
            "endpoint": source.endpoint,
            "model": source.model,
            "auth_configured": bool(source.auth_configured),
            "capabilities": list(source.capabilities),
            "selected_as_primary_for": list(source.selected_as_primary_for),
            "metadata": thaw_json_value(source.metadata),
            "max_context_tokens": source.max_context_tokens,
            "max_output_tokens": source.max_output_tokens,
        }
    )


def ai_capability_operator_read(source: Any) -> AICapabilityOperatorRead:
    return AICapabilityOperatorRead.model_validate(
        {
            "capability": source.capability,
            "enabled": bool(source.enabled),
            "health_state": source.health_state,
            "provider_available": bool(source.provider_available),
            "allow_degraded_fallback": bool(source.allow_degraded_fallback),
            "preferred_context_format": source.preferred_context_format,
            "allowed_context_formats": list(source.allowed_context_formats),
            "configured_providers": list(source.configured_providers),
            "primary_provider": source.primary_provider,
        }
    )


def ai_prompt_operator_read(source: Any) -> AIPromptOperatorRead:
    is_mapping = isinstance(source, dict)
    task = source.get("task", "") if is_mapping else source.task
    vars_json = thaw_json_value(source.get("vars_json", {}) if is_mapping else source.vars_json)
    policy = get_prompt_task_policy(task)
    capability = source.get("capability") if is_mapping else getattr(source, "capability", None)
    schema_contract = source.get("schema_contract") if is_mapping else getattr(source, "schema_contract", None)
    style_profile = source.get("style_profile") if is_mapping else getattr(source, "style_profile", None)
    return AIPromptOperatorRead.model_validate(
        {
            "id": source.get("id") if is_mapping else getattr(source, "id", None),
            "name": source.get("name") if is_mapping else source.name,
            "capability": capability if capability is not None else None if policy is None else policy.capability,
            "task": task,
            "version": int(source.get("version") if is_mapping else source.version),
            "editable": bool(source.get("editable") if is_mapping else source.editable),
            "source": source.get("source") if is_mapping else source.source,
            "is_active": bool(source.get("is_active") if is_mapping else source.is_active),
            "template": source.get("template") if is_mapping else source.template,
            "vars_json": vars_json,
            "schema_contract": thaw_json_value(
                schema_contract if schema_contract is not None else None if policy is None else policy.schema_contract
            ),
            "style_profile": style_profile if style_profile is not None else prompt_style_profile(vars_json),
            "updated_at": source.get("updated_at") if is_mapping else getattr(source, "updated_at", None),
        }
    )


def observability_overview_read(overview: Any) -> ObservabilityOverviewRead:
    return ObservabilityOverviewRead.model_validate(observability_overview_payload(overview))
