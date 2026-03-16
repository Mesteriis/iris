from src.apps.control_plane.contracts import AuditActor, RouteMutationCommand, RouteStatusChangeCommand
from src.apps.control_plane.engines.route_engine import route_to_snapshot
from src.apps.control_plane.models import EventRoute
from src.apps.control_plane.read_models import EventRouteReadModel, route_read_model_from_orm
from src.apps.control_plane.repositories import (
    EventConsumerRepository,
    EventDefinitionRepository,
    EventRouteAuditLogRepository,
    EventRouteRepository,
)
from src.core.db.uow import BaseAsyncUnitOfWork

from .audit_service import AuditLogService
from .route_mutation_writer import RouteMutationWriter
from .side_effects import ControlPlaneSideEffectDispatcher


class RouteManagementService:
    def __init__(
        self,
        uow: BaseAsyncUnitOfWork,
        *,
        dispatcher: ControlPlaneSideEffectDispatcher | None = None,
        audit_service: AuditLogService | None = None,
    ) -> None:
        self._uow = uow
        self._session = uow.session
        self._events = EventDefinitionRepository(self._session)
        self._consumers = EventConsumerRepository(self._session)
        self._routes = EventRouteRepository(self._session)
        self._dispatcher = dispatcher or ControlPlaneSideEffectDispatcher(uow)
        self._audit = audit_service or AuditLogService(EventRouteAuditLogRepository(self._session))
        self._writer = RouteMutationWriter(
            uow=uow,
            events=self._events,
            consumers=self._consumers,
            routes=self._routes,
        )

    async def list_routes(self) -> tuple[EventRouteReadModel, ...]:
        return tuple(route_read_model_from_orm(route) for route in await self._routes.list_all())

    async def create_route(self, command: RouteMutationCommand, *, actor: AuditActor) -> EventRouteReadModel:
        route, result = await self._writer.create(command)
        result = route_read_model_from_orm(route)
        await self._audit.log_route_change(
            route=route,
            route_key=route.route_key,
            action="created",
            actor=actor,
            before={},
            after=route_to_snapshot(result),
        )
        self._dispatcher.publish_route_created(route=result, actor=actor)
        self._dispatcher.invalidate_cache(reason="route_created", route_key=route.route_key, actor=actor)
        return result

    async def update_route(
        self,
        route_key: str,
        command: RouteMutationCommand,
        *,
        actor: AuditActor,
    ) -> EventRouteReadModel:
        route = await self._writer.require_route(route_key)
        before = route_to_snapshot(route_read_model_from_orm(route))
        result = await self._writer.update(route, command)
        await self._audit.log_route_change(
            route=route,
            route_key=route.route_key,
            action="updated",
            actor=actor,
            before=before,
            after=route_to_snapshot(result),
        )
        self._dispatcher.publish_route_updated(route=result, actor=actor)
        self._dispatcher.invalidate_cache(reason="route_updated", route_key=route.route_key, actor=actor)
        return result

    async def change_status(
        self,
        command: RouteStatusChangeCommand,
        *,
        actor: AuditActor,
    ) -> EventRouteReadModel:
        route = await self._writer.require_route(command.route_key)
        before = route_to_snapshot(route_read_model_from_orm(route))
        result = await self._writer.change_status(route, status=command.status.value, notes=command.notes)
        await self._audit.log_route_change(
            route=route,
            route_key=route.route_key,
            action="status_changed",
            actor=actor,
            before=before,
            after=route_to_snapshot(result),
        )
        self._dispatcher.publish_route_status_changed(route=result, actor=actor)
        self._dispatcher.invalidate_cache(reason="route_status_changed", route_key=route.route_key, actor=actor)
        return result


__all__ = ["RouteManagementService"]
