from __future__ import annotations

from typing import Any

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
    TopologyDiffItem,
)
from src.apps.control_plane.control_events import (
    CONTROL_CACHE_INVALIDATED,
    CONTROL_ROUTE_CREATED,
    CONTROL_ROUTE_STATUS_CHANGED,
    CONTROL_ROUTE_UPDATED,
    publish_control_event,
)
from src.apps.control_plane.enums import (
    EventRouteScope,
    EventRouteStatus,
    TopologyDraftChangeType,
    TopologyDraftStatus,
)
from src.apps.control_plane.exceptions import (
    EventConsumerNotFound,
    EventDefinitionNotFound,
    EventRouteCompatibilityError,
    EventRouteConflict,
    EventRouteNotFound,
    TopologyDraftNotFound,
    TopologyDraftStateError,
)
from src.apps.control_plane.models import (
    EventConsumer,
    EventDefinition,
    EventRoute,
    EventRouteAuditLog,
    TopologyConfigVersion,
    TopologyDraft,
    TopologyDraftChange,
)
from src.apps.control_plane.repositories import (
    EventConsumerRepository,
    EventDefinitionRepository,
    EventRouteAuditLogRepository,
    EventRouteRepository,
    TopologyDraftChangeRepository,
    TopologyDraftRepository,
    TopologyVersionRepository,
)
from src.apps.market_data.domain import utc_now


def route_to_snapshot(route: EventRoute) -> dict[str, Any]:
    return {
        "route_key": route.route_key,
        "event_type": route.event_definition.event_type if route.event_definition is not None else "",
        "consumer_key": route.consumer.consumer_key if route.consumer is not None else "",
        "status": route.status,
        "scope_type": route.scope_type,
        "scope_value": route.scope_value,
        "environment": route.environment,
        "filters": dict(route.filters_json or {}),
        "throttle": dict(route.throttle_config_json or {}),
        "shadow": dict(route.shadow_config_json or {}),
        "notes": route.notes,
        "priority": int(route.priority),
        "system_managed": bool(route.system_managed),
    }


def _coerce_filters(payload: dict[str, Any]) -> RouteFilters:
    return RouteFilters.from_json(payload)


def _coerce_throttle(payload: dict[str, Any]) -> RouteThrottle:
    return RouteThrottle.from_json(payload)


def _coerce_shadow(payload: dict[str, Any]) -> RouteShadow:
    return RouteShadow.from_json(payload)


class AuditLogService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = EventRouteAuditLogRepository(session)

    async def log_route_change(
        self,
        *,
        route: EventRoute | None,
        route_key: str,
        action: str,
        actor: AuditActor,
        before: dict[str, Any],
        after: dict[str, Any],
        draft_id: int | None = None,
        topology_version_id: int | None = None,
    ) -> EventRouteAuditLog:
        return await self._repository.add(
            EventRouteAuditLog(
                route_id=int(route.id) if route is not None else None,
                route_key_snapshot=route_key,
                draft_id=draft_id,
                topology_version_id=topology_version_id,
                action=action,
                actor=actor.actor,
                actor_mode=actor.actor_mode.value,
                reason=actor.reason,
                before_json=before,
                after_json=after,
                context_json=dict(actor.context),
            )
        )


class EventRegistryService:
    def __init__(self, session: AsyncSession) -> None:
        self._event_definitions = EventDefinitionRepository(session)
        self._consumers = EventConsumerRepository(session)

    async def list_event_definitions(self) -> list[EventDefinition]:
        return await self._event_definitions.list_all()

    async def list_consumers(self) -> list[EventConsumer]:
        return await self._consumers.list_all()

    async def list_compatible_consumers(self, event_type: str) -> list[EventConsumer]:
        consumers = await self._consumers.list_all()
        return [
            consumer
            for consumer in consumers
            if event_type in set(consumer.compatible_event_types_json or [])
        ]


class RouteManagementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._events = EventDefinitionRepository(session)
        self._consumers = EventConsumerRepository(session)
        self._routes = EventRouteRepository(session)
        self._audit = AuditLogService(session)

    async def list_routes(self) -> list[EventRoute]:
        return await self._routes.list_all()

    async def create_route(self, command: RouteMutationCommand, *, actor: AuditActor) -> EventRoute:
        await self._validate_route_compatibility(command.event_type, command.consumer_key)
        if await self._routes.get_by_route_key(command.route_key) is not None:
            raise EventRouteConflict(f"Route '{command.route_key}' already exists.")

        event_definition = await self._require_event_definition(command.event_type)
        consumer = await self._require_consumer(command.consumer_key)
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
        await self._audit.log_route_change(
            route=route,
            route_key=route.route_key,
            action="created",
            actor=actor,
            before={},
            after=route_to_snapshot(route),
        )
        await self._session.commit()
        publish_control_event(
            CONTROL_ROUTE_CREATED,
            {
                "route_key": route.route_key,
                "event_type": command.event_type,
                "consumer_key": command.consumer_key,
                "status": route.status,
                "actor": actor.actor,
            },
        )
        publish_control_event(
            CONTROL_CACHE_INVALIDATED,
            {"reason": "route_created", "route_key": route.route_key, "actor": actor.actor},
        )
        return route

    async def update_route(
        self,
        route_key: str,
        command: RouteMutationCommand,
        *,
        actor: AuditActor,
    ) -> EventRoute:
        route = await self._require_route(route_key)
        before = route_to_snapshot(route)
        if route.route_key != command.route_key and await self._routes.get_by_route_key(command.route_key) is not None:
            raise EventRouteConflict(f"Route '{command.route_key}' already exists.")

        await self._validate_route_compatibility(command.event_type, command.consumer_key)
        event_definition = await self._require_event_definition(command.event_type)
        consumer = await self._require_consumer(command.consumer_key)
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
        await self._session.flush()
        await self._audit.log_route_change(
            route=route,
            route_key=route.route_key,
            action="updated",
            actor=actor,
            before=before,
            after=route_to_snapshot(route),
        )
        await self._session.commit()
        publish_control_event(
            CONTROL_ROUTE_UPDATED,
            {
                "route_key": route.route_key,
                "event_type": command.event_type,
                "consumer_key": command.consumer_key,
                "status": route.status,
                "actor": actor.actor,
            },
        )
        publish_control_event(
            CONTROL_CACHE_INVALIDATED,
            {"reason": "route_updated", "route_key": route.route_key, "actor": actor.actor},
        )
        return route

    async def change_status(
        self,
        command: RouteStatusChangeCommand,
        *,
        actor: AuditActor,
    ) -> EventRoute:
        route = await self._require_route(command.route_key)
        before = route_to_snapshot(route)
        route.status = command.status.value
        route.updated_at = utc_now()
        if command.notes is not None:
            route.notes = command.notes
        await self._session.flush()
        await self._audit.log_route_change(
            route=route,
            route_key=route.route_key,
            action="status_changed",
            actor=actor,
            before=before,
            after=route_to_snapshot(route),
        )
        await self._session.commit()
        publish_control_event(
            CONTROL_ROUTE_STATUS_CHANGED,
            {
                "route_key": route.route_key,
                "status": route.status,
                "actor": actor.actor,
            },
        )
        publish_control_event(
            CONTROL_CACHE_INVALIDATED,
            {"reason": "route_status_changed", "route_key": route.route_key, "actor": actor.actor},
        )
        return route

    async def _require_event_definition(self, event_type: str) -> EventDefinition:
        event_definition = await self._events.get_by_event_type(event_type)
        if event_definition is None:
            raise EventDefinitionNotFound(f"Event definition '{event_type}' does not exist.")
        return event_definition

    async def _require_consumer(self, consumer_key: str) -> EventConsumer:
        consumer = await self._consumers.get_by_consumer_key(consumer_key)
        if consumer is None:
            raise EventConsumerNotFound(f"Event consumer '{consumer_key}' does not exist.")
        return consumer

    async def _require_route(self, route_key: str) -> EventRoute:
        route = await self._routes.get_by_route_key(route_key)
        if route is None:
            raise EventRouteNotFound(f"Route '{route_key}' does not exist.")
        return route

    async def _validate_route_compatibility(self, event_type: str, consumer_key: str) -> None:
        event_definition = await self._require_event_definition(event_type)
        consumer = await self._require_consumer(consumer_key)
        if event_definition.event_type not in set(consumer.compatible_event_types_json or []):
            raise EventRouteCompatibilityError(
                f"Consumer '{consumer_key}' is not compatible with event '{event_type}'."
            )


class TopologyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._events = EventDefinitionRepository(session)
        self._consumers = EventConsumerRepository(session)
        self._routes = EventRouteRepository(session)
        self._versions = TopologyVersionRepository(session)

    async def list_routes(self) -> list[EventRoute]:
        return await self._routes.list_all()

    async def get_latest_version(self) -> TopologyConfigVersion | None:
        return await self._versions.get_latest_published()

    async def build_snapshot(self) -> dict[str, Any]:
        latest_version = await self._versions.get_latest_published()
        routes = await self._routes.list_all()
        events = await self._events.list_all()
        consumers = await self._consumers.list_all()
        return {
            "version_number": int(latest_version.version_number) if latest_version is not None else 0,
            "created_at": latest_version.created_at.isoformat() if latest_version is not None else None,
            "events": [
                {
                    "event_type": event.event_type,
                    "display_name": event.display_name,
                    "domain": event.domain,
                    "is_control_event": bool(event.is_control_event),
                }
                for event in events
            ],
            "consumers": [
                {
                    "consumer_key": consumer.consumer_key,
                    "display_name": consumer.display_name,
                    "domain": consumer.domain,
                    "delivery_stream": consumer.delivery_stream,
                    "compatible_event_types": list(consumer.compatible_event_types_json or []),
                }
                for consumer in consumers
            ],
            "routes": [route_to_snapshot(route) for route in routes],
        }


class TopologyDraftService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._drafts = TopologyDraftRepository(session)
        self._changes = TopologyDraftChangeRepository(session)
        self._routes = EventRouteRepository(session)
        self._versions = TopologyVersionRepository(session)

    async def create_draft(self, command: DraftCreateCommand) -> TopologyDraft:
        latest_version = await self._versions.get_latest_published()
        draft = TopologyDraft(
            name=command.name,
            description=command.description,
            status=TopologyDraftStatus.DRAFT.value,
            access_mode=command.access_mode.value,
            base_version_id=int(latest_version.id) if latest_version is not None else None,
            created_by=command.created_by,
        )
        draft = await self._drafts.add(draft)
        await self._session.commit()
        return draft

    async def list_drafts(self) -> list[TopologyDraft]:
        return await self._drafts.list_all()

    async def add_change(self, draft_id: int, command: DraftChangeCommand) -> TopologyDraftChange:
        draft = await self._require_draft(draft_id)
        if draft.status != TopologyDraftStatus.DRAFT.value:
            raise TopologyDraftStateError(f"Draft '{draft_id}' is not editable.")
        change = TopologyDraftChange(
            draft_id=int(draft.id),
            change_type=command.change_type.value,
            target_route_key=command.target_route_key,
            payload_json=dict(command.payload),
            created_by=command.created_by,
        )
        change = await self._changes.add(change)
        draft.updated_at = utc_now()
        await self._session.flush()
        await self._session.commit()
        return change

    async def preview_diff(self, draft_id: int) -> list[TopologyDiffItem]:
        draft = await self._require_draft(draft_id)
        if draft.status != TopologyDraftStatus.DRAFT.value:
            raise TopologyDraftStateError(f"Draft '{draft_id}' is not editable.")

        live_routes = await self._routes.list_all()
        route_map = {route.route_key: route_to_snapshot(route) for route in live_routes}
        changes = await self._changes.list_by_draft(int(draft.id))
        diff_items: list[TopologyDiffItem] = []

        for change in changes:
            change_type = TopologyDraftChangeType(change.change_type)
            payload = dict(change.payload_json or {})
            target_route_key = change.target_route_key
            if change_type == TopologyDraftChangeType.ROUTE_CREATED:
                command = RouteMutationCommand(
                    event_type=str(payload["event_type"]),
                    consumer_key=str(payload["consumer_key"]),
                    status=EventRouteStatus(str(payload.get("status", EventRouteStatus.ACTIVE.value))),
                    scope_type=payload_scope_type(payload.get("scope_type")),
                    scope_value=str(payload["scope_value"]) if payload.get("scope_value") is not None else None,
                    environment=str(payload.get("environment", "*")),
                    filters=_coerce_filters(dict(payload.get("filters") or {})),
                    throttle=_coerce_throttle(dict(payload.get("throttle") or {})),
                    shadow=_coerce_shadow(dict(payload.get("shadow") or {})),
                    notes=str(payload["notes"]) if payload.get("notes") is not None else None,
                    priority=int(payload.get("priority", 100)),
                    system_managed=bool(payload.get("system_managed", False)),
                )
                after = {
                    "route_key": command.route_key,
                    "event_type": command.event_type,
                    "consumer_key": command.consumer_key,
                    "status": command.status.value,
                    "scope_type": command.scope_type.value,
                    "scope_value": command.scope_value,
                    "environment": command.environment,
                    "filters": command.filters.to_json(),
                    "throttle": command.throttle.to_json(),
                    "shadow": command.shadow.to_json(),
                    "notes": command.notes,
                    "priority": int(command.priority),
                    "system_managed": bool(command.system_managed),
                }
                route_map[command.route_key] = after
                diff_items.append(
                    TopologyDiffItem(
                        change_type=change_type,
                        route_key=command.route_key,
                        before={},
                        after=after,
                    )
                )
                continue

            if target_route_key is None:
                continue
            before = dict(route_map.get(target_route_key, {}))
            after = dict(before)
            if change_type == TopologyDraftChangeType.ROUTE_DELETED:
                route_map.pop(target_route_key, None)
                diff_items.append(
                    TopologyDiffItem(
                        change_type=change_type,
                        route_key=target_route_key,
                        before=before,
                        after={},
                    )
                )
                continue
            if change_type == TopologyDraftChangeType.ROUTE_STATUS_CHANGED:
                after["status"] = str(payload["status"])
                if payload.get("notes") is not None:
                    after["notes"] = str(payload["notes"])
            elif change_type == TopologyDraftChangeType.ROUTE_UPDATED:
                after.update(payload)
            route_map[target_route_key] = after
            diff_items.append(
                TopologyDiffItem(
                    change_type=change_type,
                    route_key=target_route_key,
                    before=before,
                    after=after,
                )
            )
        return diff_items

    async def _require_draft(self, draft_id: int) -> TopologyDraft:
        draft = await self._drafts.get(draft_id)
        if draft is None:
            raise TopologyDraftNotFound(f"Draft '{draft_id}' does not exist.")
        return draft


def payload_scope_type(value: Any) -> Any:
    if value is None:
        return EventRouteScope.GLOBAL
    return EventRouteScope(str(value))


__all__ = [
    "AuditLogService",
    "EventRegistryService",
    "RouteManagementService",
    "TopologyDraftService",
    "TopologyService",
    "route_to_snapshot",
]
