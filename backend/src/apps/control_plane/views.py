from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

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
from src.apps.control_plane.enums import TopologyAccessMode
from src.apps.control_plane.exceptions import (
    EventRouteCompatibilityError,
    EventRouteConflict,
    EventRouteNotFound,
    TopologyDraftNotFound,
    TopologyDraftStateError,
)
from src.apps.control_plane.query_services import (
    AuditLogQueryService,
    EventRegistryQueryService,
    RouteQueryService,
    TopologyDraftQueryService,
    TopologyObservabilityQueryService,
    TopologyQueryService,
    observability_overview_payload,
    topology_graph_payload,
    topology_snapshot_payload,
)
from src.apps.control_plane.schemas import (
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
from src.apps.control_plane.services import RouteManagementService, TopologyDraftService
from src.core.db.persistence import thaw_json_value
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow
from src.core.settings import get_settings

router = APIRouter(prefix="/control-plane", tags=["control-plane"])
DB_UOW = Depends(get_uow)


def _parse_access_mode(value: str | None) -> TopologyAccessMode:
    raw = (value or "observe").strip().lower()
    try:
        return TopologyAccessMode(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-IRIS-Access-Mode must be 'observe' or 'control'.",
        ) from exc


def _build_actor(
    *,
    actor: str | None,
    access_mode: str | None,
    reason: str | None,
) -> AuditActor:
    return AuditActor(
        actor=actor or "api",
        actor_mode=_parse_access_mode(access_mode),
        reason=reason,
        context={"surface": "http"},
    )


async def require_control_actor(
    x_iris_actor: str | None = Header(default=None, alias="X-IRIS-Actor"),
    x_iris_access_mode: str | None = Header(default="observe", alias="X-IRIS-Access-Mode"),
    x_iris_reason: str | None = Header(default=None, alias="X-IRIS-Reason"),
    x_iris_control_token: str | None = Header(default=None, alias="X-IRIS-Control-Token"),
) -> AuditActor:
    mode = _parse_access_mode(x_iris_access_mode)
    if mode != TopologyAccessMode.CONTROL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Control mode is required for topology mutations.",
        )
    settings = get_settings()
    if settings.control_plane_token and x_iris_control_token != settings.control_plane_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Control token is missing or invalid.",
        )
    return _build_actor(actor=x_iris_actor, access_mode=mode.value, reason=x_iris_reason)


CONTROL_ACTOR = Depends(require_control_actor)


def _route_payload_to_command(payload: EventRouteMutationWrite) -> RouteMutationCommand:
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


def _event_definition_read(item: Any) -> EventDefinitionRead:
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


def _event_consumer_read(item: Any) -> EventConsumerRead:
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


def _compatible_consumer_read(item: Any) -> CompatibleConsumerRead:
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


def _route_read(source: Any) -> EventRouteRead:
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


def _draft_read(source: Any) -> TopologyDraftRead:
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


def _draft_change_read(source: Any) -> TopologyDraftChangeRead:
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


def _audit_log_read(source: Any) -> EventRouteAuditLogRead:
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


@router.get("/registry/events", response_model=list[EventDefinitionRead])
async def read_event_registry(uow: BaseAsyncUnitOfWork = DB_UOW) -> list[EventDefinitionRead]:
    items = await EventRegistryQueryService(uow.session).list_event_definitions()
    return [_event_definition_read(item) for item in items]


@router.get("/registry/consumers", response_model=list[EventConsumerRead])
async def read_consumer_registry(uow: BaseAsyncUnitOfWork = DB_UOW) -> list[EventConsumerRead]:
    items = await EventRegistryQueryService(uow.session).list_consumers()
    return [_event_consumer_read(item) for item in items]


@router.get("/registry/events/{event_type}/compatible-consumers", response_model=list[CompatibleConsumerRead])
async def read_compatible_consumers(
    event_type: str,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[CompatibleConsumerRead]:
    service = EventRegistryQueryService(uow.session)
    if await service.get_event_definition(event_type) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event definition '{event_type}' was not found.",
        )
    return [_compatible_consumer_read(item) for item in await service.list_compatible_consumers(event_type)]


@router.get("/routes", response_model=list[EventRouteRead])
async def read_routes(uow: BaseAsyncUnitOfWork = DB_UOW) -> list[EventRouteRead]:
    items = await RouteQueryService(uow.session).list_routes()
    return [_route_read(route) for route in items]


@router.post("/routes", response_model=EventRouteRead, status_code=status.HTTP_201_CREATED)
async def create_route(
    payload: EventRouteMutationWrite,
    actor: AuditActor = CONTROL_ACTOR,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> EventRouteRead:
    service = RouteManagementService(uow)
    try:
        route = await service.create_route(_route_payload_to_command(payload), actor=actor)
    except EventRouteCompatibilityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EventRouteConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await uow.commit()
    return _route_read(route)


@router.put("/routes/{route_key:path}", response_model=EventRouteRead)
async def update_route(
    route_key: str,
    payload: EventRouteMutationWrite,
    actor: AuditActor = CONTROL_ACTOR,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> EventRouteRead:
    service = RouteManagementService(uow)
    try:
        route = await service.update_route(route_key, _route_payload_to_command(payload), actor=actor)
    except EventRouteNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EventRouteCompatibilityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EventRouteConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await uow.commit()
    return _route_read(route)


@router.post("/routes/{route_key:path}/status", response_model=EventRouteRead)
async def update_route_status(
    route_key: str,
    payload: EventRouteStatusWrite,
    actor: AuditActor = CONTROL_ACTOR,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> EventRouteRead:
    service = RouteManagementService(uow)
    try:
        route = await service.change_status(
            RouteStatusChangeCommand(route_key=route_key, status=payload.status, notes=payload.notes),
            actor=actor,
        )
    except EventRouteNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await uow.commit()
    return _route_read(route)


@router.get("/topology/snapshot", response_model=TopologySnapshotRead)
async def read_topology_snapshot(uow: BaseAsyncUnitOfWork = DB_UOW) -> TopologySnapshotRead:
    snapshot = await TopologyQueryService(uow.session).build_snapshot()
    return TopologySnapshotRead.model_validate(topology_snapshot_payload(snapshot))


@router.get("/topology/graph", response_model=TopologyGraphRead)
async def read_topology_graph(uow: BaseAsyncUnitOfWork = DB_UOW) -> TopologyGraphRead:
    graph = await TopologyQueryService(uow.session).build_graph()
    return TopologyGraphRead.model_validate(topology_graph_payload(graph))


@router.get("/drafts", response_model=list[TopologyDraftRead])
async def read_drafts(uow: BaseAsyncUnitOfWork = DB_UOW) -> list[TopologyDraftRead]:
    items = await TopologyDraftQueryService(uow.session).list_drafts()
    return [_draft_read(draft) for draft in items]


@router.post("/drafts", response_model=TopologyDraftRead, status_code=status.HTTP_201_CREATED)
async def create_draft(
    payload: TopologyDraftCreateWrite,
    actor: AuditActor = CONTROL_ACTOR,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> TopologyDraftRead:
    service = TopologyDraftService(uow)
    draft = await service.create_draft(
        DraftCreateCommand(
            name=payload.name,
            description=payload.description,
            access_mode=payload.access_mode,
            created_by=actor.actor,
        )
    )
    await uow.commit()
    return _draft_read(draft)


@router.post("/drafts/{draft_id}/changes", response_model=TopologyDraftChangeRead, status_code=status.HTTP_201_CREATED)
async def create_draft_change(
    draft_id: int,
    payload: TopologyDraftChangeWrite,
    actor: AuditActor = CONTROL_ACTOR,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> TopologyDraftChangeRead:
    service = TopologyDraftService(uow)
    try:
        change = await service.add_change(
            draft_id,
            DraftChangeCommand(
                change_type=payload.change_type,
                payload=dict(payload.payload),
                target_route_key=payload.target_route_key,
                created_by=actor.actor,
            ),
        )
    except TopologyDraftNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TopologyDraftStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await uow.commit()
    return _draft_change_read(change)


@router.get("/drafts/{draft_id}/diff", response_model=list[TopologyDiffItemRead])
async def read_draft_diff(
    draft_id: int,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[TopologyDiffItemRead]:
    try:
        diff = await TopologyDraftQueryService(uow.session).preview_diff(draft_id)
    except TopologyDraftNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TopologyDraftStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [
        TopologyDiffItemRead(
            change_type=item.change_type,
            route_key=item.route_key,
            before=thaw_json_value(item.before),
            after=thaw_json_value(item.after),
        )
        for item in diff
    ]


@router.post("/drafts/{draft_id}/apply", response_model=TopologyDraftLifecycleRead)
async def apply_draft(
    draft_id: int,
    actor: AuditActor = CONTROL_ACTOR,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> TopologyDraftLifecycleRead:
    service = TopologyDraftService(uow)
    try:
        draft, version = await service.apply_draft(draft_id, actor=actor)
    except TopologyDraftNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TopologyDraftStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await uow.commit()
    return TopologyDraftLifecycleRead(
        draft=_draft_read(draft),
        published_version_number=int(version.version_number),
    )


@router.post("/drafts/{draft_id}/discard", response_model=TopologyDraftLifecycleRead)
async def discard_draft(
    draft_id: int,
    actor: AuditActor = CONTROL_ACTOR,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> TopologyDraftLifecycleRead:
    service = TopologyDraftService(uow)
    try:
        draft = await service.discard_draft(draft_id, actor=actor)
    except TopologyDraftNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TopologyDraftStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await uow.commit()
    return TopologyDraftLifecycleRead(draft=_draft_read(draft), published_version_number=None)


@router.get("/audit", response_model=list[EventRouteAuditLogRead])
async def read_audit_log(
    limit: int = Query(default=50, ge=1, le=500),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[EventRouteAuditLogRead]:
    items = await AuditLogQueryService(uow.session).list_recent(limit=limit)
    return [_audit_log_read(item) for item in items]


@router.get("/observability", response_model=ObservabilityOverviewRead)
async def read_observability(uow: BaseAsyncUnitOfWork = DB_UOW) -> ObservabilityOverviewRead:
    payload = observability_overview_payload(await TopologyObservabilityQueryService(uow.session).build_overview())
    return ObservabilityOverviewRead.model_validate(payload)
