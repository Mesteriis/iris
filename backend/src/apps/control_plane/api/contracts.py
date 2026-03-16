from src.apps.control_plane.contracts import (
    AuditActor,
    DraftChangeCommand,
    DraftCreateCommand,
    RouteFilters,
    RouteMutationCommand,
    RouteShadow,
    RouteStatusChangeCommand,
    RouteThrottle,
)
from src.apps.control_plane.schemas import (
    AICapabilityOperatorRead,
    AIPromptOperatorRead,
    AIProviderOperatorRead,
    CompatibleConsumerRead,
    EventConsumerRead,
    EventDefinitionRead,
    EventRouteAuditLogRead,
    EventRouteMutationWrite,
    EventRouteRead,
    EventRouteStatusWrite,
    ObservabilityOverviewRead,
    TopologyDiffItemRead,
    TopologyDraftChangeRead,
    TopologyDraftChangeWrite,
    TopologyDraftCreateWrite,
    TopologyDraftLifecycleRead,
    TopologyDraftRead,
    TopologyGraphRead,
    TopologySnapshotRead,
)


def route_mutation_command_from_request(payload: EventRouteMutationWrite) -> RouteMutationCommand:
    return RouteMutationCommand(
        event_type=payload.event_type,
        consumer_key=payload.consumer_key,
        status=payload.status,
        scope_type=payload.scope_type,
        scope_value=payload.scope_value,
        environment=payload.environment,
        filters=RouteFilters.from_json(payload.filters.model_dump()),
        throttle=RouteThrottle.from_json(payload.throttle.model_dump(exclude_none=True)),
        shadow=RouteShadow.from_json(payload.shadow.model_dump()),
        notes=payload.notes,
        priority=payload.priority,
        system_managed=payload.system_managed,
    )


def draft_create_command_from_request(payload: TopologyDraftCreateWrite, *, actor: AuditActor) -> DraftCreateCommand:
    return DraftCreateCommand(
        name=payload.name,
        description=payload.description,
        access_mode=payload.access_mode,
        created_by=actor.actor,
    )


def draft_change_command_from_request(payload: TopologyDraftChangeWrite, *, actor: AuditActor) -> DraftChangeCommand:
    return DraftChangeCommand(
        change_type=payload.change_type,
        payload=dict(payload.payload),
        target_route_key=payload.target_route_key,
        created_by=actor.actor,
    )


__all__ = [
    "AICapabilityOperatorRead",
    "AIPromptOperatorRead",
    "AIProviderOperatorRead",
    "AuditActor",
    "CompatibleConsumerRead",
    "EventConsumerRead",
    "EventDefinitionRead",
    "EventRouteAuditLogRead",
    "EventRouteMutationWrite",
    "EventRouteRead",
    "EventRouteStatusWrite",
    "ObservabilityOverviewRead",
    "TopologyDiffItemRead",
    "TopologyDraftChangeRead",
    "TopologyDraftChangeWrite",
    "TopologyDraftCreateWrite",
    "TopologyDraftLifecycleRead",
    "TopologyDraftRead",
    "TopologyGraphRead",
    "TopologySnapshotRead",
    "draft_change_command_from_request",
    "draft_create_command_from_request",
    "route_mutation_command_from_request",
]
