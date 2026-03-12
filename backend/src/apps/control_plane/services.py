from __future__ import annotations

from datetime import datetime
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
from src.core.settings import get_settings


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


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _int_value(payload: dict[str, str], key: str) -> int:
    raw = payload.get(key)
    return int(raw) if raw is not None else 0


def _average_latency(payload: dict[str, str]) -> float | None:
    count = _int_value(payload, "latency_count")
    if count <= 0:
        return None
    total_raw = payload.get("latency_total_ms")
    total = float(total_raw) if total_raw is not None else 0.0
    return round(total / count, 2)


def _lag_seconds(now: datetime, observed_at: datetime | None) -> int | None:
    if observed_at is None:
        return None
    return max(int((now - observed_at).total_seconds()), 0)


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

    async def build_graph(self) -> dict[str, Any]:
        latest_version = await self._versions.get_latest_published()
        routes = await self._routes.list_all()
        events = await self._events.list_all()
        consumers = await self._consumers.list_all()

        nodes = [
            {
                "id": f"event:{event.event_type}",
                "node_type": "event",
                "key": event.event_type,
                "label": event.display_name,
                "domain": event.domain,
                "metadata": {
                    "description": event.description,
                    "is_control_event": bool(event.is_control_event),
                },
            }
            for event in events
        ]
        nodes.extend(
            {
                "id": f"consumer:{consumer.consumer_key}",
                "node_type": "consumer",
                "key": consumer.consumer_key,
                "label": consumer.display_name,
                "domain": consumer.domain,
                "metadata": {
                    "delivery_stream": consumer.delivery_stream,
                    "delivery_mode": consumer.delivery_mode,
                    "supports_shadow": bool(consumer.supports_shadow),
                    "supported_filter_fields": list(consumer.supported_filter_fields_json or []),
                    "supported_scopes": list(consumer.supported_scopes_json or []),
                    "compatible_event_types": list(consumer.compatible_event_types_json or []),
                },
            }
            for consumer in consumers
        )

        compatibility = {
            event.event_type: [
                consumer.consumer_key
                for consumer in consumers
                if event.event_type in set(consumer.compatible_event_types_json or [])
            ]
            for event in events
        }
        edges = [
            {
                "id": route.route_key,
                "route_key": route.route_key,
                "source": f"event:{route.event_definition.event_type}",
                "target": f"consumer:{route.consumer.consumer_key}",
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
                "compatible": route.consumer.consumer_key in compatibility.get(route.event_definition.event_type, []),
            }
            for route in routes
        ]
        return {
            "version_number": int(latest_version.version_number) if latest_version is not None else 0,
            "created_at": latest_version.created_at.isoformat() if latest_version is not None else None,
            "nodes": nodes,
            "edges": edges,
            "palette": {
                "events": [event.event_type for event in events],
                "consumers": [consumer.consumer_key for consumer in consumers],
            },
            "compatibility": compatibility,
        }


class TopologyObservabilityService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        metrics_store: ControlPlaneMetricsStore | None = None,
        dead_consumer_after_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self._routes = EventRouteRepository(session)
        self._consumers = EventConsumerRepository(session)
        self._versions = TopologyVersionRepository(session)
        self._metrics = metrics_store or ControlPlaneMetricsStore()
        self._dead_consumer_after_seconds = (
            int(dead_consumer_after_seconds)
            if dead_consumer_after_seconds is not None
            else int(settings.control_plane_dead_consumer_after_seconds)
        )

    async def build_overview(self) -> dict[str, Any]:
        latest_version = await self._versions.get_latest_published()
        routes = await self._routes.list_all()
        consumers = await self._consumers.list_all()
        generated_at = utc_now()

        route_metrics = [
            await self._build_route_metrics(route, generated_at=generated_at)
            for route in routes
        ]
        consumer_metrics = [
            await self._build_consumer_metrics(consumer, generated_at=generated_at)
            for consumer in consumers
        ]
        return {
            "version_number": int(latest_version.version_number) if latest_version is not None else 0,
            "generated_at": generated_at.isoformat(),
            "throughput": sum(int(metric["throughput"]) for metric in route_metrics),
            "failure_count": sum(int(metric["failure_count"]) for metric in route_metrics),
            "shadow_route_count": sum(1 for route in routes if route.status == EventRouteStatus.SHADOW.value),
            "muted_route_count": sum(1 for route in routes if route.status == EventRouteStatus.MUTED.value),
            "dead_consumer_count": sum(1 for consumer in consumer_metrics if bool(consumer["dead"])),
            "routes": route_metrics,
            "consumers": consumer_metrics,
        }

    async def _build_route_metrics(self, route: EventRoute, *, generated_at: datetime) -> dict[str, Any]:
        raw = await self._metrics.read_route_metrics(route.route_key)
        last_delivered_at = _parse_datetime(raw.get("last_delivered_at"))
        last_completed_at = _parse_datetime(raw.get("last_completed_at"))
        avg_latency_ms = _average_latency(raw)
        return {
            "route_key": route.route_key,
            "event_type": route.event_definition.event_type if route.event_definition is not None else "",
            "consumer_key": route.consumer.consumer_key if route.consumer is not None else "",
            "status": route.status,
            "throughput": _int_value(raw, "delivered_total"),
            "failure_count": _int_value(raw, "failure_total"),
            "avg_latency_ms": avg_latency_ms,
            "last_delivered_at": last_delivered_at.isoformat() if last_delivered_at is not None else None,
            "last_completed_at": last_completed_at.isoformat() if last_completed_at is not None else None,
            "lag_seconds": _lag_seconds(generated_at, last_delivered_at),
            "shadow_count": _int_value(raw, "shadow_total"),
            "muted": route.status == EventRouteStatus.MUTED.value,
            "last_reason": raw.get("last_reason"),
        }

    async def _build_consumer_metrics(self, consumer: EventConsumer, *, generated_at: datetime) -> dict[str, Any]:
        raw = await self._metrics.read_consumer_metrics(consumer.consumer_key)
        last_seen_at = _parse_datetime(raw.get("last_seen_at"))
        last_failure_at = _parse_datetime(raw.get("last_failure_at"))
        lag_seconds = _lag_seconds(generated_at, last_seen_at)
        dead = lag_seconds is None or lag_seconds > self._dead_consumer_after_seconds
        return {
            "consumer_key": consumer.consumer_key,
            "domain": consumer.domain,
            "processed_total": _int_value(raw, "processed_total"),
            "failure_count": _int_value(raw, "failure_total"),
            "avg_latency_ms": _average_latency(raw),
            "last_seen_at": last_seen_at.isoformat() if last_seen_at is not None else None,
            "last_failure_at": last_failure_at.isoformat() if last_failure_at is not None else None,
            "lag_seconds": lag_seconds,
            "dead": dead,
            "supports_shadow": bool(consumer.supports_shadow),
            "delivery_stream": consumer.delivery_stream,
            "last_error": raw.get("last_error"),
        }


class TopologyDraftService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._drafts = TopologyDraftRepository(session)
        self._changes = TopologyDraftChangeRepository(session)
        self._routes = EventRouteRepository(session)
        self._events = EventDefinitionRepository(session)
        self._consumers = EventConsumerRepository(session)
        self._versions = TopologyVersionRepository(session)
        self._audit = AuditLogService(session)

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
                command = _command_from_payload(payload)
                after = _command_to_route_snapshot(command)
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
                route_key = target_route_key
            elif change_type == TopologyDraftChangeType.ROUTE_UPDATED:
                merged_payload = dict(after)
                merged_payload.update(payload)
                command = _command_from_payload(merged_payload)
                after = _command_to_route_snapshot(command)
                route_key = command.route_key
            else:
                route_key = target_route_key
            if route_key != target_route_key:
                route_map.pop(target_route_key, None)
            route_map[route_key] = after
            diff_items.append(
                TopologyDiffItem(
                    change_type=change_type,
                    route_key=route_key,
                    before=before,
                    after=after,
                )
            )
        return diff_items

    async def apply_draft(self, draft_id: int, *, actor: AuditActor) -> tuple[TopologyDraft, TopologyConfigVersion]:
        draft = await self._require_draft(draft_id)
        if draft.status != TopologyDraftStatus.DRAFT.value:
            raise TopologyDraftStateError(f"Draft '{draft_id}' is not editable.")

        latest_version = await self._versions.get_latest_published()
        latest_version_id = int(latest_version.id) if latest_version is not None else None
        if draft.base_version_id != latest_version_id:
            raise TopologyDraftStateError(
                f"Draft '{draft_id}' is stale and must be rebased on the latest published topology."
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
        await self._session.flush()
        await self._session.commit()

        publish_control_event(
            CONTROL_TOPOLOGY_PUBLISHED,
            {
                "draft_id": int(draft.id),
                "version_number": int(version.version_number),
                "actor": actor.actor,
            },
        )
        publish_control_event(
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
                before=dict(item.before),
                after=dict(item.after),
                draft_id=int(draft.id),
            )
        draft.status = TopologyDraftStatus.DISCARDED.value
        draft.discarded_at = utc_now()
        draft.updated_at = draft.discarded_at
        await self._session.flush()
        await self._session.commit()
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
            await self._session.flush()
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
        topology_service = TopologyService(self._session)
        snapshot = await topology_service.build_snapshot()
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
        await self._session.flush()
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
