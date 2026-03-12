from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

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
from src.apps.control_plane.models import EventRoute, EventRouteAuditLog, TopologyDraft, TopologyDraftChange
from src.apps.control_plane.schemas import (
    CompatibleConsumerRead,
    ConsumerObservabilityRead,
    EventConsumerRead,
    EventDefinitionRead,
    EventRouteAuditLogRead,
    EventRouteMutationWrite,
    EventRouteRead,
    EventRouteStatusWrite,
    ObservabilityOverviewRead,
    RouteFiltersPayload,
    RouteObservabilityRead,
    RouteShadowPayload,
    RouteThrottlePayload,
    TopologyDiffItemRead,
    TopologyDraftChangeRead,
    TopologyDraftChangeWrite,
    TopologyDraftCreateWrite,
    TopologyDraftLifecycleRead,
    TopologyDraftRead,
    TopologyGraphRead,
    TopologySnapshotRead,
)
from src.apps.control_plane.services import (
    AuditLogService,
    EventRegistryService,
    RouteManagementService,
    TopologyDraftService,
    TopologyObservabilityService,
    TopologyService,
)
from src.core.db.session import get_db
from src.core.settings import get_settings

router = APIRouter(prefix="/control-plane", tags=["control-plane"])
DB_SESSION = Depends(get_db)


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


def _route_read(route: EventRoute) -> EventRouteRead:
    return EventRouteRead(
        id=int(route.id),
        route_key=route.route_key,
        event_type=route.event_definition.event_type if route.event_definition is not None else "",
        consumer_key=route.consumer.consumer_key if route.consumer is not None else "",
        status=route.status,
        scope_type=route.scope_type,
        scope_value=route.scope_value,
        environment=route.environment,
        filters=RouteFiltersPayload.model_validate(route.filters_json or {}),
        throttle=RouteThrottlePayload.model_validate(route.throttle_config_json or {}),
        shadow=RouteShadowPayload.model_validate(route.shadow_config_json or {}),
        notes=route.notes,
        priority=int(route.priority),
        system_managed=bool(route.system_managed),
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


def _draft_read(draft: TopologyDraft) -> TopologyDraftRead:
    return TopologyDraftRead.model_validate(
        {
            "id": int(draft.id),
            "name": draft.name,
            "description": draft.description,
            "status": draft.status,
            "access_mode": draft.access_mode,
            "base_version_id": draft.base_version_id,
            "created_by": draft.created_by,
            "applied_version_id": draft.applied_version_id,
            "created_at": draft.created_at,
            "updated_at": draft.updated_at,
            "applied_at": draft.applied_at,
            "discarded_at": draft.discarded_at,
        }
    )


def _draft_change_read(change: TopologyDraftChange) -> TopologyDraftChangeRead:
    return TopologyDraftChangeRead.model_validate(
        {
            "id": int(change.id),
            "draft_id": int(change.draft_id),
            "change_type": change.change_type,
            "target_route_key": change.target_route_key,
            "payload_json": dict(change.payload_json or {}),
            "created_by": change.created_by,
            "created_at": change.created_at,
        }
    )


def _audit_log_read(row: EventRouteAuditLog) -> EventRouteAuditLogRead:
    return EventRouteAuditLogRead.model_validate(
        {
            "id": int(row.id),
            "route_key_snapshot": row.route_key_snapshot,
            "action": row.action,
            "actor": row.actor,
            "actor_mode": row.actor_mode,
            "reason": row.reason,
            "before_json": dict(row.before_json or {}),
            "after_json": dict(row.after_json or {}),
            "context_json": dict(row.context_json or {}),
            "created_at": row.created_at,
        }
    )


@router.get("/registry/events", response_model=list[EventDefinitionRead])
async def read_event_registry(db: AsyncSession = DB_SESSION) -> list[EventDefinitionRead]:
    service = EventRegistryService(db)
    return [EventDefinitionRead.model_validate(row) for row in await service.list_event_definitions()]


@router.get("/registry/consumers", response_model=list[EventConsumerRead])
async def read_consumer_registry(db: AsyncSession = DB_SESSION) -> list[EventConsumerRead]:
    service = EventRegistryService(db)
    return [EventConsumerRead.model_validate(row) for row in await service.list_consumers()]


@router.get("/registry/events/{event_type}/compatible-consumers", response_model=list[CompatibleConsumerRead])
async def read_compatible_consumers(event_type: str, db: AsyncSession = DB_SESSION) -> list[CompatibleConsumerRead]:
    service = EventRegistryService(db)
    definitions = await service.list_event_definitions()
    if event_type not in {row.event_type for row in definitions}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event definition '{event_type}' was not found.",
        )
    return [
        CompatibleConsumerRead(
            consumer_key=row.consumer_key,
            display_name=row.display_name,
            domain=row.domain,
            supports_shadow=bool(row.supports_shadow),
            supported_filter_fields=list(row.supported_filter_fields_json or []),
            supported_scopes=list(row.supported_scopes_json or []),
        )
        for row in await service.list_compatible_consumers(event_type)
    ]


@router.get("/routes", response_model=list[EventRouteRead])
async def read_routes(db: AsyncSession = DB_SESSION) -> list[EventRouteRead]:
    service = RouteManagementService(db)
    return [_route_read(route) for route in await service.list_routes()]


@router.post("/routes", response_model=EventRouteRead, status_code=status.HTTP_201_CREATED)
async def create_route(
    payload: EventRouteMutationWrite,
    actor: AuditActor = CONTROL_ACTOR,
    db: AsyncSession = DB_SESSION,
) -> EventRouteRead:
    service = RouteManagementService(db)
    try:
        route = await service.create_route(_route_payload_to_command(payload), actor=actor)
    except EventRouteCompatibilityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EventRouteConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _route_read(route)


@router.put("/routes/{route_key:path}", response_model=EventRouteRead)
async def update_route(
    route_key: str,
    payload: EventRouteMutationWrite,
    actor: AuditActor = CONTROL_ACTOR,
    db: AsyncSession = DB_SESSION,
) -> EventRouteRead:
    service = RouteManagementService(db)
    try:
        route = await service.update_route(route_key, _route_payload_to_command(payload), actor=actor)
    except EventRouteNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EventRouteCompatibilityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EventRouteConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _route_read(route)


@router.post("/routes/{route_key:path}/status", response_model=EventRouteRead)
async def update_route_status(
    route_key: str,
    payload: EventRouteStatusWrite,
    actor: AuditActor = CONTROL_ACTOR,
    db: AsyncSession = DB_SESSION,
) -> EventRouteRead:
    service = RouteManagementService(db)
    try:
        route = await service.change_status(
            RouteStatusChangeCommand(route_key=route_key, status=payload.status, notes=payload.notes),
            actor=actor,
        )
    except EventRouteNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _route_read(route)


@router.get("/topology/snapshot", response_model=TopologySnapshotRead)
async def read_topology_snapshot(db: AsyncSession = DB_SESSION) -> TopologySnapshotRead:
    service = TopologyService(db)
    return TopologySnapshotRead.model_validate(await service.build_snapshot())


@router.get("/topology/graph", response_model=TopologyGraphRead)
async def read_topology_graph(db: AsyncSession = DB_SESSION) -> TopologyGraphRead:
    service = TopologyService(db)
    return TopologyGraphRead.model_validate(await service.build_graph())


@router.get("/drafts", response_model=list[TopologyDraftRead])
async def read_drafts(db: AsyncSession = DB_SESSION) -> list[TopologyDraftRead]:
    service = TopologyDraftService(db)
    return [_draft_read(draft) for draft in await service.list_drafts()]


@router.post("/drafts", response_model=TopologyDraftRead, status_code=status.HTTP_201_CREATED)
async def create_draft(
    payload: TopologyDraftCreateWrite,
    actor: AuditActor = CONTROL_ACTOR,
    db: AsyncSession = DB_SESSION,
) -> TopologyDraftRead:
    service = TopologyDraftService(db)
    draft = await service.create_draft(
        DraftCreateCommand(
            name=payload.name,
            description=payload.description,
            access_mode=payload.access_mode,
            created_by=actor.actor,
        )
    )
    return _draft_read(draft)


@router.post("/drafts/{draft_id}/changes", response_model=TopologyDraftChangeRead, status_code=status.HTTP_201_CREATED)
async def create_draft_change(
    draft_id: int,
    payload: TopologyDraftChangeWrite,
    actor: AuditActor = CONTROL_ACTOR,
    db: AsyncSession = DB_SESSION,
) -> TopologyDraftChangeRead:
    service = TopologyDraftService(db)
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
    return _draft_change_read(change)


@router.get("/drafts/{draft_id}/diff", response_model=list[TopologyDiffItemRead])
async def read_draft_diff(draft_id: int, db: AsyncSession = DB_SESSION) -> list[TopologyDiffItemRead]:
    service = TopologyDraftService(db)
    try:
        diff = await service.preview_diff(draft_id)
    except TopologyDraftNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TopologyDraftStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [
        TopologyDiffItemRead(
            change_type=item.change_type,
            route_key=item.route_key,
            before=dict(item.before),
            after=dict(item.after),
        )
        for item in diff
    ]


@router.post("/drafts/{draft_id}/apply", response_model=TopologyDraftLifecycleRead)
async def apply_draft(
    draft_id: int,
    actor: AuditActor = CONTROL_ACTOR,
    db: AsyncSession = DB_SESSION,
) -> TopologyDraftLifecycleRead:
    service = TopologyDraftService(db)
    try:
        draft, version = await service.apply_draft(draft_id, actor=actor)
    except TopologyDraftNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TopologyDraftStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TopologyDraftLifecycleRead(
        draft=_draft_read(draft),
        published_version_number=int(version.version_number),
    )


@router.post("/drafts/{draft_id}/discard", response_model=TopologyDraftLifecycleRead)
async def discard_draft(
    draft_id: int,
    actor: AuditActor = CONTROL_ACTOR,
    db: AsyncSession = DB_SESSION,
) -> TopologyDraftLifecycleRead:
    service = TopologyDraftService(db)
    try:
        draft = await service.discard_draft(draft_id, actor=actor)
    except TopologyDraftNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TopologyDraftStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TopologyDraftLifecycleRead(draft=_draft_read(draft), published_version_number=None)


@router.get("/audit", response_model=list[EventRouteAuditLogRead])
async def read_audit_log(
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = DB_SESSION,
) -> list[EventRouteAuditLogRead]:
    service = AuditLogService(db)
    return [_audit_log_read(row) for row in await service.list_recent(limit=limit)]


@router.get("/observability", response_model=ObservabilityOverviewRead)
async def read_observability(db: AsyncSession = DB_SESSION) -> ObservabilityOverviewRead:
    service = TopologyObservabilityService(db)
    payload = await service.build_overview()
    return ObservabilityOverviewRead(
        version_number=int(payload["version_number"]),
        generated_at=payload["generated_at"],
        throughput=int(payload["throughput"]),
        failure_count=int(payload["failure_count"]),
        shadow_route_count=int(payload["shadow_route_count"]),
        muted_route_count=int(payload["muted_route_count"]),
        dead_consumer_count=int(payload["dead_consumer_count"]),
        routes=[RouteObservabilityRead.model_validate(row) for row in payload["routes"]],
        consumers=[ConsumerObservabilityRead.model_validate(row) for row in payload["consumers"]],
    )
