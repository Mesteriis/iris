from typing import Any

from iris.apps.control_plane.contracts import AuditActor, RouteMutationCommand
from iris.apps.control_plane.engines.route_engine import route_to_snapshot
from iris.apps.control_plane.enums import EventAuditAction
from iris.apps.control_plane.models import EventRoute
from iris.apps.control_plane.read_models import EventRouteReadModel

from .audit_service import AuditLogService
from .route_mutation_writer import RouteMutationWriter


class DraftRouteMutationFlow:
    def __init__(self, *, writer: RouteMutationWriter, audit_service: AuditLogService) -> None:
        self._writer = writer
        self._audit = audit_service

    async def create(
        self,
        command: RouteMutationCommand,
        *,
        actor: AuditActor,
        draft_id: int,
        topology_version_id: int,
    ) -> EventRouteReadModel:
        route, result = await self._writer.create(command)
        await self._audit.log_route_change(
            route=route,
            route_key=route.route_key,
            action=EventAuditAction.CREATED.value,
            actor=actor,
            before={},
            after=route_to_snapshot(result),
            draft_id=draft_id,
            topology_version_id=topology_version_id,
        )
        return result

    async def update(
        self,
        route: EventRoute,
        *,
        command: RouteMutationCommand,
        actor: AuditActor,
        draft_id: int,
        topology_version_id: int,
        before: dict[str, Any],
    ) -> EventRouteReadModel:
        result = await self._writer.update(route, command)
        await self._audit.log_route_change(
            route=route,
            route_key=route.route_key,
            action=EventAuditAction.UPDATED.value,
            actor=actor,
            before=before,
            after=route_to_snapshot(result),
            draft_id=draft_id,
            topology_version_id=topology_version_id,
        )
        return result


__all__ = ["DraftRouteMutationFlow"]
