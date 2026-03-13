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
    CONTROL_TOPOLOGY_PUBLISHED,
    publish_control_event,
)
from src.apps.control_plane.enums import (
    EventAuditAction,
    EventRouteScope,
    EventRouteStatus,
    TopologyDraftChangeType,
    TopologyDraftStatus,
    TopologyVersionStatus,
)
from src.apps.control_plane.exceptions import (
    EventConsumerNotFound,
    EventDefinitionNotFound,
    EventRouteCompatibilityError,
    EventRouteConflict,
    EventRouteNotFound,
    TopologyDraftConcurrencyConflict,
    TopologyDraftNotFound,
    TopologyDraftStateError,
)
from src.apps.control_plane.metrics import ControlPlaneMetricsStore
from src.apps.control_plane.models import (
    EventConsumer,
    EventDefinition,
    EventRoute,
    EventRouteAuditLog,
    TopologyConfigVersion,
    TopologyDraft,
    TopologyDraftChange,
)
from src.apps.control_plane.query_services import (
    TopologyDraftQueryService,
    TopologyObservabilityQueryService,
    TopologyQueryService,
    observability_overview_payload,
    topology_graph_payload,
    topology_snapshot_payload,
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
from src.core.db.persistence import thaw_json_value
from src.core.db.uow import BaseAsyncUnitOfWork


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


def _command_to_route_snapshot(command: RouteMutationCommand) -> dict[str, Any]:
    return {
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


def _command_from_payload(payload: dict[str, Any]) -> RouteMutationCommand:
    return RouteMutationCommand(
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

    async def list_recent(self, *, limit: int = 100) -> list[EventRouteAuditLog]:
        return await self._repository.list_recent(limit=limit)


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
        return [consumer for consumer in consumers if event_type in set(consumer.compatible_event_types_json or [])]


class RouteManagementService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._session = uow.session
        self._events = EventDefinitionRepository(self._session)
        self._consumers = EventConsumerRepository(self._session)
        self._routes = EventRouteRepository(self._session)
        self._audit = AuditLogService(self._session)

    def _publish_after_commit(self, event_type: str, payload: dict[str, object]) -> None:
        self._uow.add_after_commit_action(
            lambda event_type=event_type, payload=dict(payload): publish_control_event(event_type, payload)
        )

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
        self._publish_after_commit(
            CONTROL_ROUTE_CREATED,
            {
                "route_key": route.route_key,
                "event_type": command.event_type,
                "consumer_key": command.consumer_key,
                "status": route.status,
                "actor": actor.actor,
            },
        )
        self._publish_after_commit(
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
        await self._uow.flush()
        await self._audit.log_route_change(
            route=route,
            route_key=route.route_key,
            action="updated",
            actor=actor,
            before=before,
            after=route_to_snapshot(route),
        )
        self._publish_after_commit(
            CONTROL_ROUTE_UPDATED,
            {
                "route_key": route.route_key,
                "event_type": command.event_type,
                "consumer_key": command.consumer_key,
                "status": route.status,
                "actor": actor.actor,
            },
        )
        self._publish_after_commit(
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
        await self._uow.flush()
        await self._audit.log_route_change(
            route=route,
            route_key=route.route_key,
            action="status_changed",
            actor=actor,
            before=before,
            after=route_to_snapshot(route),
        )
        self._publish_after_commit(
            CONTROL_ROUTE_STATUS_CHANGED,
            {
                "route_key": route.route_key,
                "status": route.status,
                "actor": actor.actor,
            },
        )
        self._publish_after_commit(
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
        self._versions = TopologyVersionRepository(session)

    async def list_routes(self) -> list[EventRoute]:
        return await EventRouteRepository(self._session).list_all()

    async def get_latest_version(self) -> TopologyConfigVersion | None:
        return await self._versions.get_latest_published()

    async def build_snapshot(self) -> dict[str, Any]:
        return topology_snapshot_payload(await TopologyQueryService(self._session).build_snapshot())

    async def build_graph(self) -> dict[str, Any]:
        return topology_graph_payload(await TopologyQueryService(self._session).build_graph())


class TopologyObservabilityService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        metrics_store: ControlPlaneMetricsStore | None = None,
        dead_consumer_after_seconds: int | None = None,
    ) -> None:
        self._query_service = TopologyObservabilityQueryService(
            session,
            metrics_store=metrics_store,
            dead_consumer_after_seconds=dead_consumer_after_seconds,
        )

    async def build_overview(self) -> dict[str, Any]:
        return observability_overview_payload(await self._query_service.build_overview())


class TopologyDraftService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._session = uow.session
        self._drafts = TopologyDraftRepository(self._session)
        self._changes = TopologyDraftChangeRepository(self._session)
        self._routes = EventRouteRepository(self._session)
        self._events = EventDefinitionRepository(self._session)
        self._consumers = EventConsumerRepository(self._session)
        self._versions = TopologyVersionRepository(self._session)
        self._audit = AuditLogService(self._session)

    def _publish_after_commit(self, event_type: str, payload: dict[str, object]) -> None:
        self._uow.add_after_commit_action(
            lambda event_type=event_type, payload=dict(payload): publish_control_event(event_type, payload)
        )

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
        await self._uow.flush()
        return change

    async def preview_diff(self, draft_id: int) -> list[TopologyDiffItem]:
        return list(await TopologyDraftQueryService(self._session).preview_diff(draft_id))

    async def apply_draft(self, draft_id: int, *, actor: AuditActor) -> tuple[TopologyDraft, TopologyConfigVersion]:
        draft = await self._require_draft(draft_id)
        if draft.status != TopologyDraftStatus.DRAFT.value:
            raise TopologyDraftStateError(f"Draft '{draft_id}' is not editable.")

        latest_version = await self._versions.get_latest_published()
        latest_version_id = int(latest_version.id) if latest_version is not None else None
        if draft.base_version_id != latest_version_id:
            raise TopologyDraftConcurrencyConflict(
                draft_id,
                expected_version=int(draft.base_version.version_number) if draft.base_version is not None else None,
                current_version=int(latest_version.version_number) if latest_version is not None else None,
            )

        changes = await self._changes.list_by_draft(int(draft.id))
        if not changes:
            raise TopologyDraftStateError(f"Draft '{draft_id}' has no changes to apply.")

        next_version_number = (int(latest_version.version_number) if latest_version is not None else 0) + 1
        version = await self._versions.add(
            TopologyConfigVersion(
                version_number=next_version_number,
                status=TopologyVersionStatus.PUBLISHED.value,
                summary=f"Applied draft '{draft.name}'",
                published_by=actor.actor,
                snapshot_json={},
            )
        )
        for change in changes:
            await self._apply_change(
                change,
                draft_id=int(draft.id),
                topology_version_id=int(version.id),
                actor=actor,
            )
        snapshot = await self._build_published_snapshot(version=version)
        version.snapshot_json = snapshot
        draft.status = TopologyDraftStatus.APPLIED.value
        draft.applied_version_id = int(version.id)
        draft.applied_at = utc_now()
        draft.updated_at = draft.applied_at
        await self._uow.flush()
        self._publish_after_commit(
            CONTROL_TOPOLOGY_PUBLISHED,
            {
                "draft_id": int(draft.id),
                "version_number": int(version.version_number),
                "actor": actor.actor,
            },
        )
        self._publish_after_commit(
            CONTROL_CACHE_INVALIDATED,
            {
                "reason": "topology_published",
                "draft_id": int(draft.id),
                "version_number": int(version.version_number),
                "actor": actor.actor,
            },
        )
        return draft, version

    async def discard_draft(self, draft_id: int, *, actor: AuditActor) -> TopologyDraft:
        draft = await self._require_draft(draft_id)
        if draft.status != TopologyDraftStatus.DRAFT.value:
            raise TopologyDraftStateError(f"Draft '{draft_id}' cannot be discarded from status '{draft.status}'.")

        for item in await self.preview_diff(draft_id):
            await self._audit.log_route_change(
                route=None,
                route_key=item.route_key,
                action=EventAuditAction.DRAFT_DISCARDED.value,
                actor=actor,
                before=thaw_json_value(item.before),
                after=thaw_json_value(item.after),
                draft_id=int(draft.id),
            )
        draft.status = TopologyDraftStatus.DISCARDED.value
        draft.discarded_at = utc_now()
        draft.updated_at = draft.discarded_at
        await self._uow.flush()
        return draft

    async def _apply_change(
        self,
        change: TopologyDraftChange,
        *,
        draft_id: int,
        topology_version_id: int,
        actor: AuditActor,
    ) -> None:
        change_type = TopologyDraftChangeType(change.change_type)
        payload = dict(change.payload_json or {})
        if change_type == TopologyDraftChangeType.ROUTE_CREATED:
            command = _command_from_payload(payload)
            await self._create_route_from_command(
                command,
                actor=actor,
                draft_id=draft_id,
                topology_version_id=topology_version_id,
            )
            return

        if change.target_route_key is None:
            raise TopologyDraftStateError(f"Draft change '{change.id}' is missing a target route key.")

        route = await self._require_route(change.target_route_key)
        before = route_to_snapshot(route)
        if change_type == TopologyDraftChangeType.ROUTE_STATUS_CHANGED:
            route.status = str(payload["status"])
            if payload.get("notes") is not None:
                route.notes = str(payload["notes"])
            route.updated_at = utc_now()
            await self._uow.flush()
            await self._audit.log_route_change(
                route=route,
                route_key=route.route_key,
                action=EventAuditAction.STATUS_CHANGED.value,
                actor=actor,
                before=before,
                after=route_to_snapshot(route),
                draft_id=draft_id,
                topology_version_id=topology_version_id,
            )
            return

        if change_type == TopologyDraftChangeType.ROUTE_UPDATED:
            merged_payload = dict(before)
            merged_payload.update(payload)
            command = _command_from_payload(merged_payload)
            await self._update_route_from_command(
                route,
                command=command,
                actor=actor,
                draft_id=draft_id,
                topology_version_id=topology_version_id,
                before=before,
            )
            return

        if change_type == TopologyDraftChangeType.ROUTE_DELETED:
            await self._routes.delete(route)
            await self._audit.log_route_change(
                route=None,
                route_key=before["route_key"],
                action=EventAuditAction.DELETED.value,
                actor=actor,
                before=before,
                after={},
                draft_id=draft_id,
                topology_version_id=topology_version_id,
            )
            return

        raise TopologyDraftStateError(f"Unsupported draft change type '{change.change_type}'.")

    async def _require_draft(self, draft_id: int) -> TopologyDraft:
        draft = await self._drafts.get(draft_id)
        if draft is None:
            raise TopologyDraftNotFound(f"Draft '{draft_id}' does not exist.")
        return draft

    async def _build_published_snapshot(self, *, version: TopologyConfigVersion) -> dict[str, Any]:
        snapshot = topology_snapshot_payload(await TopologyQueryService(self._session).build_snapshot())
        snapshot["version_number"] = int(version.version_number)
        snapshot["created_at"] = version.created_at.isoformat() if version.created_at is not None else None
        return snapshot

    async def _create_route_from_command(
        self,
        command: RouteMutationCommand,
        *,
        actor: AuditActor,
        draft_id: int,
        topology_version_id: int,
    ) -> EventRoute:
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
            action=EventAuditAction.CREATED.value,
            actor=actor,
            before={},
            after=route_to_snapshot(route),
            draft_id=draft_id,
            topology_version_id=topology_version_id,
        )
        return route

    async def _update_route_from_command(
        self,
        route: EventRoute,
        *,
        command: RouteMutationCommand,
        actor: AuditActor,
        draft_id: int,
        topology_version_id: int,
        before: dict[str, Any],
    ) -> EventRoute:
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
        await self._uow.flush()
        await self._audit.log_route_change(
            route=route,
            route_key=route.route_key,
            action=EventAuditAction.UPDATED.value,
            actor=actor,
            before=before,
            after=route_to_snapshot(route),
            draft_id=draft_id,
            topology_version_id=topology_version_id,
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


def payload_scope_type(value: Any) -> Any:
    if value is None:
        return EventRouteScope.GLOBAL
    return EventRouteScope(str(value))


__all__ = [
    "AuditLogService",
    "EventRegistryService",
    "RouteManagementService",
    "TopologyDraftService",
    "TopologyObservabilityService",
    "TopologyService",
    "route_to_snapshot",
]
