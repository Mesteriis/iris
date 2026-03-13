from __future__ import annotations

from fastapi import APIRouter, status

from src.apps.control_plane.api.contracts import (
    EventRouteMutationWrite,
    EventRouteRead,
    EventRouteStatusWrite,
    TopologyDraftChangeRead,
    TopologyDraftChangeWrite,
    TopologyDraftCreateWrite,
    TopologyDraftLifecycleRead,
    TopologyDraftRead,
    draft_change_command_from_request,
    draft_create_command_from_request,
    route_mutation_command_from_request,
)
from src.apps.control_plane.api.deps import ControlActorDep, DraftCommandDep, RouteCommandDep
from src.apps.control_plane.api.errors import control_plane_error_to_http
from src.apps.control_plane.api.presenters import (
    draft_lifecycle_read,
    route_read,
    topology_draft_change_read,
    topology_draft_read,
)
from src.apps.control_plane.contracts import RouteStatusChangeCommand
from src.core.http.command_executor import execute_command

router = APIRouter(tags=["control-plane:commands"])


@router.post("/routes", response_model=EventRouteRead, status_code=status.HTTP_201_CREATED)
async def create_route(
    payload: EventRouteMutationWrite,
    actor: ControlActorDep,
    commands: RouteCommandDep,
) -> EventRouteRead:
    return await execute_command(
        action=lambda: commands.service.create_route(route_mutation_command_from_request(payload), actor=actor),
        uow=commands.uow,
        presenter=route_read,
        translate_error=control_plane_error_to_http,
    )


@router.put("/routes/{route_key:path}", response_model=EventRouteRead)
async def update_route(
    route_key: str,
    payload: EventRouteMutationWrite,
    actor: ControlActorDep,
    commands: RouteCommandDep,
) -> EventRouteRead:
    return await execute_command(
        action=lambda: commands.service.update_route(route_key, route_mutation_command_from_request(payload), actor=actor),
        uow=commands.uow,
        presenter=route_read,
        translate_error=control_plane_error_to_http,
    )


@router.post("/routes/{route_key:path}/status", response_model=EventRouteRead)
async def update_route_status(
    route_key: str,
    payload: EventRouteStatusWrite,
    actor: ControlActorDep,
    commands: RouteCommandDep,
) -> EventRouteRead:
    return await execute_command(
        action=lambda: commands.service.change_status(
            RouteStatusChangeCommand(route_key=route_key, status=payload.status, notes=payload.notes),
            actor=actor,
        ),
        uow=commands.uow,
        presenter=route_read,
        translate_error=control_plane_error_to_http,
    )


@router.post("/drafts", response_model=TopologyDraftRead, status_code=status.HTTP_201_CREATED)
async def create_draft(
    payload: TopologyDraftCreateWrite,
    actor: ControlActorDep,
    commands: DraftCommandDep,
) -> TopologyDraftRead:
    return await execute_command(
        action=lambda: commands.service.create_draft(draft_create_command_from_request(payload, actor=actor)),
        uow=commands.uow,
        presenter=topology_draft_read,
        translate_error=control_plane_error_to_http,
    )


@router.post("/drafts/{draft_id}/changes", response_model=TopologyDraftChangeRead, status_code=status.HTTP_201_CREATED)
async def create_draft_change(
    draft_id: int,
    payload: TopologyDraftChangeWrite,
    actor: ControlActorDep,
    commands: DraftCommandDep,
) -> TopologyDraftChangeRead:
    return await execute_command(
        action=lambda: commands.service.add_change(
            draft_id,
            draft_change_command_from_request(payload, actor=actor),
        ),
        uow=commands.uow,
        presenter=topology_draft_change_read,
        translate_error=control_plane_error_to_http,
    )


@router.post("/drafts/{draft_id}/apply", response_model=TopologyDraftLifecycleRead)
async def apply_draft(
    draft_id: int,
    actor: ControlActorDep,
    commands: DraftCommandDep,
) -> TopologyDraftLifecycleRead:
    return await execute_command(
        action=lambda: commands.service.apply_draft(draft_id, actor=actor),
        uow=commands.uow,
        presenter=draft_lifecycle_read,
        translate_error=control_plane_error_to_http,
    )


@router.post("/drafts/{draft_id}/discard", response_model=TopologyDraftLifecycleRead)
async def discard_draft(
    draft_id: int,
    actor: ControlActorDep,
    commands: DraftCommandDep,
) -> TopologyDraftLifecycleRead:
    return await execute_command(
        action=lambda: commands.service.discard_draft(draft_id, actor=actor),
        uow=commands.uow,
        presenter=draft_lifecycle_read,
        translate_error=control_plane_error_to_http,
    )
