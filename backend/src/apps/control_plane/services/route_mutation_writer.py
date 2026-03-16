from src.apps.control_plane.contracts import RouteMutationCommand
from src.apps.control_plane.exceptions import (
    EventConsumerNotFound,
    EventDefinitionNotFound,
    EventRouteCompatibilityError,
    EventRouteConflict,
    EventRouteNotFound,
)
from src.apps.control_plane.models import EventConsumer, EventDefinition, EventRoute
from src.apps.control_plane.read_models import EventRouteReadModel, route_read_model_from_orm
from src.apps.control_plane.repositories import (
    EventConsumerRepository,
    EventDefinitionRepository,
    EventRouteRepository,
)
from src.apps.market_data.domain import utc_now
from src.core.db.uow import BaseAsyncUnitOfWork


class RouteMutationWriter:
    def __init__(
        self,
        *,
        uow: BaseAsyncUnitOfWork,
        events: EventDefinitionRepository,
        consumers: EventConsumerRepository,
        routes: EventRouteRepository,
    ) -> None:
        self._uow = uow
        self._events = events
        self._consumers = consumers
        self._routes = routes

    async def create(self, command: RouteMutationCommand) -> tuple[EventRoute, EventRouteReadModel]:
        await self.validate_route_compatibility(command.event_type, command.consumer_key)
        if await self._routes.get_by_route_key(command.route_key) is not None:
            raise EventRouteConflict(f"Route '{command.route_key}' already exists.")

        event_definition = await self.require_event_definition(command.event_type)
        consumer = await self.require_consumer(command.consumer_key)
        route = EventRoute(
            route_key=command.route_key,
            event_definition_id=int(event_definition.id),
            consumer_id=int(consumer.id),
            status=command.status.value,
            scope_type=command.scope_type.value,
            scope_value=command.scope_value,
            environment=command.environment,
            filters_json=command.filters.to_json(),
            throttle_config_json=command.throttle.to_json(),
            shadow_config_json=command.shadow.to_json(),
            notes=command.notes,
            priority=int(command.priority),
            system_managed=bool(command.system_managed),
        )
        route = await self._routes.add(route)
        route.event_definition = event_definition
        route.consumer = consumer
        return route, route_read_model_from_orm(route)

    async def update(self, route: EventRoute, command: RouteMutationCommand) -> EventRouteReadModel:
        if route.route_key != command.route_key and await self._routes.get_by_route_key(command.route_key) is not None:
            raise EventRouteConflict(f"Route '{command.route_key}' already exists.")

        await self.validate_route_compatibility(command.event_type, command.consumer_key)
        event_definition = await self.require_event_definition(command.event_type)
        consumer = await self.require_consumer(command.consumer_key)
        route.route_key = command.route_key
        route.event_definition_id = int(event_definition.id)
        route.consumer_id = int(consumer.id)
        route.status = command.status.value
        route.scope_type = command.scope_type.value
        route.scope_value = command.scope_value
        route.environment = command.environment
        route.filters_json = command.filters.to_json()
        route.throttle_config_json = command.throttle.to_json()
        route.shadow_config_json = command.shadow.to_json()
        route.notes = command.notes
        route.priority = int(command.priority)
        route.system_managed = bool(command.system_managed)
        route.updated_at = utc_now()
        route.event_definition = event_definition
        route.consumer = consumer
        await self._uow.flush()
        return route_read_model_from_orm(route)

    async def change_status(self, route: EventRoute, *, status: str, notes: str | None = None) -> EventRouteReadModel:
        route.status = status
        route.updated_at = utc_now()
        if notes is not None:
            route.notes = notes
        await self._uow.flush()
        return route_read_model_from_orm(route)

    async def require_event_definition(self, event_type: str) -> EventDefinition:
        event_definition = await self._events.get_by_event_type(event_type)
        if event_definition is None:
            raise EventDefinitionNotFound(f"Event definition '{event_type}' does not exist.")
        return event_definition

    async def require_consumer(self, consumer_key: str) -> EventConsumer:
        consumer = await self._consumers.get_by_consumer_key(consumer_key)
        if consumer is None:
            raise EventConsumerNotFound(f"Event consumer '{consumer_key}' does not exist.")
        return consumer

    async def require_route(self, route_key: str) -> EventRoute:
        route = await self._routes.get_by_route_key(route_key)
        if route is None:
            raise EventRouteNotFound(f"Route '{route_key}' does not exist.")
        return route

    async def validate_route_compatibility(self, event_type: str, consumer_key: str) -> None:
        event_definition = await self.require_event_definition(event_type)
        consumer = await self.require_consumer(consumer_key)
        if event_definition.event_type not in set(consumer.compatible_event_types_json or []):
            raise EventRouteCompatibilityError(
                f"Consumer '{consumer_key}' is not compatible with event '{event_type}'."
            )


__all__ = ["RouteMutationWriter"]
