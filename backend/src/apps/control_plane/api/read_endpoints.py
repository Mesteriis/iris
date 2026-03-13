from __future__ import annotations

from fastapi import APIRouter, Query

from src.apps.control_plane.api.contracts import (
    CompatibleConsumerRead,
    EventConsumerRead,
    EventDefinitionRead,
    EventRouteAuditLogRead,
    EventRouteRead,
    ObservabilityOverviewRead,
    TopologyDiffItemRead,
    TopologyDraftRead,
    TopologyGraphRead,
    TopologySnapshotRead,
)
from src.apps.control_plane.api.deps import (
    AuditLogQueryDep,
    EventRegistryQueryDep,
    RouteQueryDep,
    TopologyDraftQueryDep,
    TopologyObservabilityQueryDep,
    TopologyQueryDep,
)
from src.apps.control_plane.api.errors import control_plane_error_to_http, event_definition_not_found_error
from src.apps.control_plane.api.presenters import (
    audit_log_read,
    compatible_consumer_read,
    event_consumer_read,
    event_definition_read,
    observability_overview_read,
    route_read,
    topology_diff_item_read,
    topology_draft_read,
    topology_graph_read,
    topology_snapshot_read,
)

router = APIRouter(tags=["control-plane:read"])


@router.get("/registry/events", response_model=list[EventDefinitionRead])
async def read_event_registry(service: EventRegistryQueryDep) -> list[EventDefinitionRead]:
    return [event_definition_read(item) for item in await service.list_event_definitions()]


@router.get("/registry/consumers", response_model=list[EventConsumerRead])
async def read_consumer_registry(service: EventRegistryQueryDep) -> list[EventConsumerRead]:
    return [event_consumer_read(item) for item in await service.list_consumers()]


@router.get("/registry/events/{event_type}/compatible-consumers", response_model=list[CompatibleConsumerRead])
async def read_compatible_consumers(
    event_type: str,
    service: EventRegistryQueryDep,
) -> list[CompatibleConsumerRead]:
    if await service.get_event_definition(event_type) is None:
        raise event_definition_not_found_error(event_type)
    return [compatible_consumer_read(item) for item in await service.list_compatible_consumers(event_type)]


@router.get("/routes", response_model=list[EventRouteRead])
async def read_routes(service: RouteQueryDep) -> list[EventRouteRead]:
    return [route_read(route) for route in await service.list_routes()]


@router.get("/topology/snapshot", response_model=TopologySnapshotRead)
async def read_topology_snapshot(service: TopologyQueryDep) -> TopologySnapshotRead:
    return topology_snapshot_read(await service.build_snapshot())


@router.get("/topology/graph", response_model=TopologyGraphRead)
async def read_topology_graph(service: TopologyQueryDep) -> TopologyGraphRead:
    return topology_graph_read(await service.build_graph())


@router.get("/drafts", response_model=list[TopologyDraftRead])
async def read_drafts(service: TopologyDraftQueryDep) -> list[TopologyDraftRead]:
    return [topology_draft_read(draft) for draft in await service.list_drafts()]


@router.get("/drafts/{draft_id}/diff", response_model=list[TopologyDiffItemRead])
async def read_draft_diff(
    draft_id: int,
    service: TopologyDraftQueryDep,
) -> list[TopologyDiffItemRead]:
    try:
        items = await service.preview_diff(draft_id)
    except Exception as exc:
        http_error = control_plane_error_to_http(exc)
        if http_error is not None:
            raise http_error from exc
        raise
    return [topology_diff_item_read(item) for item in items]


@router.get("/audit", response_model=list[EventRouteAuditLogRead])
async def read_audit_log(
    service: AuditLogQueryDep,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[EventRouteAuditLogRead]:
    return [audit_log_read(item) for item in await service.list_recent(limit=limit)]


@router.get("/observability", response_model=ObservabilityOverviewRead)
async def read_observability(service: TopologyObservabilityQueryDep) -> ObservabilityOverviewRead:
    return observability_overview_read(await service.build_overview())
