from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.control_plane.contracts import (
    TopologyDiffItem,
)
from src.apps.control_plane.engines import preview_topology_diff, route_to_snapshot
from src.apps.control_plane.enums import (
    EventRouteStatus,
    TopologyDraftStatus,
)
from src.apps.control_plane.exceptions import TopologyDraftNotFound, TopologyDraftStateError
from src.apps.control_plane.metrics import ControlPlaneMetricsStore
from src.apps.control_plane.read_models import (
    AICapabilityOperatorReadModel,
    AIPromptOperatorReadModel,
    AIProviderOperatorReadModel,
    CompatibleConsumerReadModel,
    ConsumerObservabilityReadModel,
    EventConsumerReadModel,
    EventDefinitionReadModel,
    EventRouteAuditLogReadModel,
    EventRouteReadModel,
    ObservabilityOverviewReadModel,
    RouteObservabilityReadModel,
    TopologyConsumerSnapshotReadModel,
    TopologyDraftChangeReadModel,
    TopologyDraftReadModel,
    TopologyEdgeReadModel,
    TopologyEventSnapshotReadModel,
    TopologyGraphReadModel,
    TopologyNodeReadModel,
    TopologySnapshotReadModel,
    event_consumer_read_model_from_orm,
    event_definition_read_model_from_orm,
    event_route_audit_log_read_model_from_orm,
    route_read_model_from_orm,
    topology_draft_change_read_model_from_orm,
    topology_draft_read_model_from_orm,
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
from src.apps.hypothesis_engine.query_services import HypothesisQueryService
from src.apps.market_data.domain import utc_now
from src.core.ai.capabilities import get_capability_policy
from src.core.ai.contracts import AICapability
from src.core.ai.health import capability_health_state
from src.core.ai.prompt_policy import get_prompt_task_policy, list_builtin_prompt_definitions, prompt_style_profile
from src.core.ai.settings import build_provider_configs
from src.core.db.persistence import AsyncQueryService, freeze_json_value
from src.core.settings import get_settings


def route_snapshot_payload_from_read_model(route: EventRouteReadModel) -> dict[str, Any]:
    return route_to_snapshot(route)


def topology_snapshot_payload(snapshot: TopologySnapshotReadModel) -> dict[str, Any]:
    return {
        "version_number": int(snapshot.version_number),
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at is not None else None,
        "events": [
            {
                "event_type": item.event_type,
                "display_name": item.display_name,
                "domain": item.domain,
                "is_control_event": bool(item.is_control_event),
            }
            for item in snapshot.events
        ],
        "consumers": [
            {
                "consumer_key": item.consumer_key,
                "display_name": item.display_name,
                "domain": item.domain,
                "delivery_stream": item.delivery_stream,
                "compatible_event_types": list(item.compatible_event_types),
            }
            for item in snapshot.consumers
        ],
        "routes": [route_snapshot_payload_from_read_model(route) for route in snapshot.routes],
    }


def topology_graph_payload(graph: TopologyGraphReadModel) -> dict[str, Any]:
    return {
        "version_number": int(graph.version_number),
        "created_at": graph.created_at.isoformat() if graph.created_at is not None else None,
        "nodes": [
            {
                "id": node.id,
                "node_type": node.node_type,
                "key": node.key,
                "label": node.label,
                "domain": node.domain,
                "metadata": dict(node.metadata),
            }
            for node in graph.nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "route_key": edge.route_key,
                "source": edge.source,
                "target": edge.target,
                "status": edge.status.value,
                "scope_type": edge.scope_type.value,
                "scope_value": edge.scope_value,
                "environment": edge.environment,
                "filters": edge.filters.to_json(),
                "throttle": edge.throttle.to_json(),
                "shadow": edge.shadow.to_json(),
                "notes": edge.notes,
                "priority": int(edge.priority),
                "system_managed": bool(edge.system_managed),
                "compatible": bool(edge.compatible),
            }
            for edge in graph.edges
        ],
        "palette": {str(key): list(value) for key, value in dict(graph.palette).items()},
        "compatibility": {str(key): list(value) for key, value in dict(graph.compatibility).items()},
    }


def observability_overview_payload(overview: ObservabilityOverviewReadModel) -> dict[str, Any]:
    return {
        "version_number": int(overview.version_number),
        "generated_at": overview.generated_at.isoformat(),
        "throughput": int(overview.throughput),
        "failure_count": int(overview.failure_count),
        "shadow_route_count": int(overview.shadow_route_count),
        "muted_route_count": int(overview.muted_route_count),
        "dead_consumer_count": int(overview.dead_consumer_count),
        "routes": [
            {
                "route_key": route.route_key,
                "event_type": route.event_type,
                "consumer_key": route.consumer_key,
                "status": route.status.value,
                "throughput": int(route.throughput),
                "failure_count": int(route.failure_count),
                "avg_latency_ms": route.avg_latency_ms,
                "last_delivered_at": route.last_delivered_at.isoformat() if route.last_delivered_at else None,
                "last_completed_at": route.last_completed_at.isoformat() if route.last_completed_at else None,
                "lag_seconds": route.lag_seconds,
                "shadow_count": int(route.shadow_count),
                "muted": bool(route.muted),
                "last_reason": route.last_reason,
            }
            for route in overview.routes
        ],
        "consumers": [
            {
                "consumer_key": consumer.consumer_key,
                "domain": consumer.domain,
                "processed_total": int(consumer.processed_total),
                "failure_count": int(consumer.failure_count),
                "avg_latency_ms": consumer.avg_latency_ms,
                "last_seen_at": consumer.last_seen_at.isoformat() if consumer.last_seen_at else None,
                "last_failure_at": consumer.last_failure_at.isoformat() if consumer.last_failure_at else None,
                "lag_seconds": consumer.lag_seconds,
                "dead": bool(consumer.dead),
                "supports_shadow": bool(consumer.supports_shadow),
                "delivery_stream": consumer.delivery_stream,
                "last_error": consumer.last_error,
            }
            for consumer in overview.consumers
        ],
    }


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


class EventRegistryQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="control_plane", service_name="EventRegistryQueryService")
        self._events = EventDefinitionRepository(session)
        self._consumers = EventConsumerRepository(session)

    async def list_event_definitions(self) -> tuple[EventDefinitionReadModel, ...]:
        self._log_debug("query.list_event_definitions", mode="read")
        items = tuple(event_definition_read_model_from_orm(row) for row in await self._events.list_all())
        self._log_debug("query.list_event_definitions.result", mode="read", count=len(items))
        return items

    async def get_event_definition(self, event_type: str) -> EventDefinitionReadModel | None:
        self._log_debug("query.get_event_definition", mode="read", event_type=event_type)
        row = await self._events.get_by_event_type(event_type)
        if row is None:
            self._log_debug("query.get_event_definition.result", mode="read", found=False)
            return None
        item = event_definition_read_model_from_orm(row)
        self._log_debug("query.get_event_definition.result", mode="read", found=True)
        return item

    async def list_consumers(self) -> tuple[EventConsumerReadModel, ...]:
        self._log_debug("query.list_event_consumers", mode="read")
        items = tuple(event_consumer_read_model_from_orm(row) for row in await self._consumers.list_all())
        self._log_debug("query.list_event_consumers.result", mode="read", count=len(items))
        return items

    async def list_compatible_consumers(self, event_type: str) -> tuple[CompatibleConsumerReadModel, ...]:
        self._log_debug("query.list_compatible_consumers", mode="read", event_type=event_type)
        consumers = await self.list_consumers()
        items = tuple(
            CompatibleConsumerReadModel(
                consumer_key=consumer.consumer_key,
                display_name=consumer.display_name,
                domain=consumer.domain,
                supports_shadow=consumer.supports_shadow,
                supported_filter_fields=consumer.supported_filter_fields_json,
                supported_scopes=consumer.supported_scopes_json,
            )
            for consumer in consumers
            if event_type in set(consumer.compatible_event_types_json)
        )
        self._log_debug("query.list_compatible_consumers.result", mode="read", count=len(items))
        return items


class RouteQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="control_plane", service_name="RouteQueryService")
        self._routes = EventRouteRepository(session)

    async def list_routes(self) -> tuple[EventRouteReadModel, ...]:
        self._log_debug("query.list_routes", mode="read", loading_profile="with_relations")
        items = tuple(route_read_model_from_orm(route) for route in await self._routes.list_all())
        self._log_debug("query.list_routes.result", mode="read", count=len(items))
        return items

    async def get_detail(self, route_key: str) -> EventRouteReadModel | None:
        self._log_debug("query.get_route_detail", mode="read", route_key=route_key, loading_profile="with_relations")
        route = await self._routes.get_by_route_key(route_key)
        if route is None:
            self._log_debug("query.get_route_detail.result", mode="read", found=False)
            return None
        item = route_read_model_from_orm(route)
        self._log_debug("query.get_route_detail.result", mode="read", found=True)
        return item


class TopologyQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="control_plane", service_name="TopologyQueryService")
        self._events = EventDefinitionRepository(session)
        self._consumers = EventConsumerRepository(session)
        self._routes = EventRouteRepository(session)
        self._versions = TopologyVersionRepository(session)

    async def build_snapshot(self) -> TopologySnapshotReadModel:
        self._log_debug("query.build_topology_snapshot", mode="read")
        latest_version = await self._versions.get_latest_published()
        routes = tuple(route_read_model_from_orm(route) for route in await self._routes.list_all())
        events = tuple(
            TopologyEventSnapshotReadModel(
                event_type=row.event_type,
                display_name=row.display_name,
                domain=row.domain,
                is_control_event=bool(row.is_control_event),
            )
            for row in await self._events.list_all()
        )
        consumers = tuple(
            TopologyConsumerSnapshotReadModel(
                consumer_key=row.consumer_key,
                display_name=row.display_name,
                domain=row.domain,
                delivery_stream=row.delivery_stream,
                compatible_event_types=tuple(str(value) for value in row.compatible_event_types_json or ()),
            )
            for row in await self._consumers.list_all()
        )
        snapshot = TopologySnapshotReadModel(
            version_number=int(latest_version.version_number) if latest_version is not None else 0,
            created_at=latest_version.created_at if latest_version is not None else None,
            events=events,
            consumers=consumers,
            routes=routes,
        )
        self._log_debug("query.build_topology_snapshot.result", mode="read", route_count=len(routes))
        return snapshot

    async def build_graph(self) -> TopologyGraphReadModel:
        self._log_debug("query.build_topology_graph", mode="read")
        latest_version = await self._versions.get_latest_published()
        routes = tuple(route_read_model_from_orm(route) for route in await self._routes.list_all())
        events = tuple(event_definition_read_model_from_orm(row) for row in await self._events.list_all())
        consumers = tuple(event_consumer_read_model_from_orm(row) for row in await self._consumers.list_all())

        nodes = tuple(
            TopologyNodeReadModel(
                id=f"event:{event.event_type}",
                node_type="event",
                key=event.event_type,
                label=event.display_name,
                domain=event.domain,
                metadata=freeze_json_value(
                    {
                        "description": event.description,
                        "is_control_event": bool(event.is_control_event),
                    }
                ),
            )
            for event in events
        ) + tuple(
            TopologyNodeReadModel(
                id=f"consumer:{consumer.consumer_key}",
                node_type="consumer",
                key=consumer.consumer_key,
                label=consumer.display_name,
                domain=consumer.domain,
                metadata=freeze_json_value(
                    {
                        "delivery_stream": consumer.delivery_stream,
                        "delivery_mode": consumer.delivery_mode,
                        "supports_shadow": bool(consumer.supports_shadow),
                        "supported_filter_fields": list(consumer.supported_filter_fields_json),
                        "supported_scopes": list(consumer.supported_scopes_json),
                        "compatible_event_types": list(consumer.compatible_event_types_json),
                    }
                ),
            )
            for consumer in consumers
        )

        compatibility = freeze_json_value(
            {
                event.event_type: tuple(
                    consumer.consumer_key
                    for consumer in consumers
                    if event.event_type in set(consumer.compatible_event_types_json)
                )
                for event in events
            }
        )
        edges = tuple(
            TopologyEdgeReadModel(
                id=route.route_key,
                route_key=route.route_key,
                source=f"event:{route.event_type}",
                target=f"consumer:{route.consumer_key}",
                status=route.status,
                scope_type=route.scope_type,
                scope_value=route.scope_value,
                environment=route.environment,
                filters=route.filters,
                throttle=route.throttle,
                shadow=route.shadow,
                notes=route.notes,
                priority=route.priority,
                system_managed=route.system_managed,
                compatible=route.consumer_key in compatibility.get(route.event_type, ()),
            )
            for route in routes
        )
        graph = TopologyGraphReadModel(
            version_number=int(latest_version.version_number) if latest_version is not None else 0,
            created_at=latest_version.created_at if latest_version is not None else None,
            nodes=nodes,
            edges=edges,
            palette=freeze_json_value(
                {
                    "events": tuple(event.event_type for event in events),
                    "consumers": tuple(consumer.consumer_key for consumer in consumers),
                }
            ),
            compatibility=compatibility,
        )
        self._log_debug("query.build_topology_graph.result", mode="read", edge_count=len(edges))
        return graph


class TopologyDraftQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="control_plane", service_name="TopologyDraftQueryService")
        self._drafts = TopologyDraftRepository(session)
        self._changes = TopologyDraftChangeRepository(session)
        self._routes = EventRouteRepository(session)

    async def list_drafts(self) -> tuple[TopologyDraftReadModel, ...]:
        self._log_debug("query.list_topology_drafts", mode="read", loading_profile="with_relations")
        items = tuple(topology_draft_read_model_from_orm(row) for row in await self._drafts.list_all())
        self._log_debug("query.list_topology_drafts.result", mode="read", count=len(items))
        return items

    async def get_detail(self, draft_id: int) -> TopologyDraftReadModel | None:
        self._log_debug(
            "query.get_topology_draft_detail", mode="read", draft_id=draft_id, loading_profile="with_relations"
        )
        draft = await self._drafts.get(draft_id)
        if draft is None:
            self._log_debug("query.get_topology_draft_detail.result", mode="read", found=False)
            return None
        item = topology_draft_read_model_from_orm(draft)
        self._log_debug("query.get_topology_draft_detail.result", mode="read", found=True)
        return item

    async def list_changes(self, draft_id: int) -> tuple[TopologyDraftChangeReadModel, ...]:
        self._log_debug("query.list_topology_draft_changes", mode="read", draft_id=draft_id)
        items = tuple(
            topology_draft_change_read_model_from_orm(row) for row in await self._changes.list_by_draft(draft_id)
        )
        self._log_debug("query.list_topology_draft_changes.result", mode="read", draft_id=draft_id, count=len(items))
        return items

    async def preview_diff(self, draft_id: int) -> tuple[TopologyDiffItem, ...]:
        self._log_debug("query.preview_topology_draft_diff", mode="read", draft_id=draft_id)
        draft = await self._drafts.get(draft_id)
        if draft is None:
            self._log_debug("query.preview_topology_draft_diff.result", mode="read", draft_id=draft_id, found=False)
            raise TopologyDraftNotFound(f"Draft '{draft_id}' does not exist.")
        if draft.status != TopologyDraftStatus.DRAFT.value:
            raise TopologyDraftStateError(f"Draft '{draft_id}' is not editable.")

        live_routes = tuple(route_read_model_from_orm(route) for route in await self._routes.list_all())
        preview_items = preview_topology_diff(live_routes=live_routes, changes=await self.list_changes(draft_id))
        items = tuple(
            TopologyDiffItem(
                change_type=item.change_type,
                route_key=item.route_key,
                before=freeze_json_value(item.before),
                after=freeze_json_value(item.after),
            )
            for item in preview_items
        )
        self._log_debug("query.preview_topology_draft_diff.result", mode="read", draft_id=draft_id, count=len(items))
        return items


class AuditLogQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="control_plane", service_name="AuditLogQueryService")
        self._repository = EventRouteAuditLogRepository(session)

    async def list_recent(self, *, limit: int = 100) -> tuple[EventRouteAuditLogReadModel, ...]:
        self._log_debug("query.list_recent_route_audit_logs", mode="read", limit=limit)
        items = tuple(
            event_route_audit_log_read_model_from_orm(row) for row in await self._repository.list_recent(limit=limit)
        )
        self._log_debug("query.list_recent_route_audit_logs.result", mode="read", count=len(items))
        return items


class TopologyObservabilityQueryService(AsyncQueryService):
    def __init__(
        self,
        session: AsyncSession,
        *,
        metrics_store: ControlPlaneMetricsStore | None = None,
        dead_consumer_after_seconds: int | None = None,
    ) -> None:
        super().__init__(session, domain="control_plane", service_name="TopologyObservabilityQueryService")
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

    async def build_overview(self) -> ObservabilityOverviewReadModel:
        self._log_debug("query.build_topology_observability_overview", mode="read")
        latest_version = await self._versions.get_latest_published()
        routes = await self._routes.list_all()
        consumers = await self._consumers.list_all()
        generated_at = utc_now()

        route_metrics = tuple(
            [
                await self._build_route_metrics(route_read_model_from_orm(route), generated_at=generated_at)
                for route in routes
            ]
        )
        consumer_metrics = tuple(
            [
                await self._build_consumer_metrics(
                    event_consumer_read_model_from_orm(consumer),
                    generated_at=generated_at,
                )
                for consumer in consumers
            ]
        )
        overview = ObservabilityOverviewReadModel(
            version_number=int(latest_version.version_number) if latest_version is not None else 0,
            generated_at=generated_at,
            throughput=sum(int(metric.throughput) for metric in route_metrics),
            failure_count=sum(int(metric.failure_count) for metric in route_metrics),
            shadow_route_count=sum(1 for route in routes if route.status == EventRouteStatus.SHADOW.value),
            muted_route_count=sum(1 for route in routes if route.status == EventRouteStatus.MUTED.value),
            dead_consumer_count=sum(1 for consumer in consumer_metrics if consumer.dead),
            routes=route_metrics,
            consumers=consumer_metrics,
        )
        self._log_debug(
            "query.build_topology_observability_overview.result",
            mode="read",
            route_count=len(route_metrics),
        )
        return overview

    async def _build_route_metrics(
        self,
        route: EventRouteReadModel,
        *,
        generated_at: datetime,
    ) -> RouteObservabilityReadModel:
        raw = await self._metrics.read_route_metrics(route.route_key)
        last_delivered_at = _parse_datetime(raw.get("last_delivered_at"))
        last_completed_at = _parse_datetime(raw.get("last_completed_at"))
        avg_latency_ms = _average_latency(raw)
        return RouteObservabilityReadModel(
            route_key=route.route_key,
            event_type=route.event_type,
            consumer_key=route.consumer_key,
            status=route.status,
            throughput=_int_value(raw, "delivered_total"),
            failure_count=_int_value(raw, "failure_total"),
            avg_latency_ms=avg_latency_ms,
            last_delivered_at=last_delivered_at,
            last_completed_at=last_completed_at,
            lag_seconds=_lag_seconds(generated_at, last_delivered_at),
            shadow_count=_int_value(raw, "shadow_total"),
            muted=route.status == EventRouteStatus.MUTED,
            last_reason=raw.get("last_reason"),
        )

    async def _build_consumer_metrics(
        self,
        consumer: EventConsumerReadModel,
        *,
        generated_at: datetime,
    ) -> ConsumerObservabilityReadModel:
        raw = await self._metrics.read_consumer_metrics(consumer.consumer_key)
        last_seen_at = _parse_datetime(raw.get("last_seen_at"))
        last_failure_at = _parse_datetime(raw.get("last_failure_at"))
        lag_seconds = _lag_seconds(generated_at, last_seen_at)
        dead = lag_seconds is None or lag_seconds > self._dead_consumer_after_seconds
        return ConsumerObservabilityReadModel(
            consumer_key=consumer.consumer_key,
            domain=consumer.domain,
            processed_total=_int_value(raw, "processed_total"),
            failure_count=_int_value(raw, "failure_total"),
            avg_latency_ms=_average_latency(raw),
            last_seen_at=last_seen_at,
            last_failure_at=last_failure_at,
            lag_seconds=lag_seconds,
            dead=dead,
            supports_shadow=consumer.supports_shadow,
            delivery_stream=consumer.delivery_stream,
            last_error=raw.get("last_error"),
        )


class AIOperatorQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession, *, settings=None) -> None:
        super().__init__(session, domain="control_plane", service_name="AIOperatorQueryService")
        self._settings = settings or get_settings()
        self._hypothesis_queries = HypothesisQueryService(session)

    async def list_ai_providers(self) -> tuple[AIProviderOperatorReadModel, ...]:
        self._log_debug("query.list_ai_providers", mode="admin")
        providers = build_provider_configs(self._settings)
        primary_by_capability = {
            capability: next(
                (
                    provider.name
                    for provider in providers
                    if provider.enabled and capability in provider.capabilities
                ),
                None,
            )
            for capability in AICapability
        }
        items = tuple(
            AIProviderOperatorReadModel(
                name=provider.name,
                kind=provider.kind,
                enabled=bool(provider.enabled),
                priority=int(provider.priority),
                base_url=provider.base_url,
                endpoint=provider.endpoint,
                model=provider.model,
                auth_configured=bool(provider.auth_token) or provider.kind.value == "local_http",
                capabilities=tuple(provider.capabilities),
                selected_as_primary_for=tuple(
                    capability
                    for capability, primary in primary_by_capability.items()
                    if primary == provider.name
                ),
                metadata=freeze_json_value(dict(provider.metadata)),
                max_context_tokens=provider.max_context_tokens,
                max_output_tokens=provider.max_output_tokens,
            )
            for provider in providers
        )
        self._log_debug("query.list_ai_providers.result", mode="admin", count=len(items))
        return items

    async def list_ai_capabilities(self) -> tuple[AICapabilityOperatorReadModel, ...]:
        self._log_debug("query.list_ai_capabilities", mode="admin")
        providers = build_provider_configs(self._settings)
        items = tuple(
            self._build_capability_record(capability, providers=providers)
            for capability in AICapability
        )
        self._log_debug("query.list_ai_capabilities.result", mode="admin", count=len(items))
        return items

    async def list_ai_prompts(
        self,
        *,
        name: str | None = None,
        capability: AICapability | None = None,
        task: str | None = None,
        editable: bool | None = None,
    ) -> tuple[AIPromptOperatorReadModel, ...]:
        self._log_debug(
            "query.list_ai_prompts",
            mode="admin",
            name=name,
            capability=capability.value if capability is not None else None,
            task=task,
            editable=editable,
        )
        db_prompts = await self._hypothesis_queries.list_prompts(name=name)
        active_db_names = {item.name for item in db_prompts if item.is_active}
        items = [self._build_db_prompt_record(prompt) for prompt in db_prompts]
        for prompt in list_builtin_prompt_definitions():
            if prompt.source == "fallback" and prompt.name in active_db_names:
                continue
            items.append(self._build_builtin_prompt_record(prompt))
        filtered = tuple(
            item
            for item in items
            if self._prompt_matches(
                item,
                name=name,
                capability=capability,
                task=task,
                editable=editable,
            )
        )
        ordered = tuple(
            sorted(
                filtered,
                key=lambda item: (
                    item.capability.value if item.capability is not None else "~",
                    item.name,
                    -int(item.version),
                    item.source,
                ),
            )
        )
        self._log_debug("query.list_ai_prompts.result", mode="admin", count=len(ordered))
        return ordered

    def _build_capability_record(
        self,
        capability: AICapability,
        *,
        providers,
    ) -> AICapabilityOperatorReadModel:
        policy = get_capability_policy(capability, settings=self._settings)
        configured_providers = tuple(
            provider.name
            for provider in providers
            if provider.enabled and capability in provider.capabilities
        )
        return AICapabilityOperatorReadModel(
            capability=capability,
            enabled=bool(policy.enabled),
            health_state=capability_health_state(capability, settings=self._settings),
            provider_available=bool(configured_providers) and bool(policy.enabled),
            allow_degraded_fallback=bool(policy.allow_degraded_fallback),
            preferred_context_format=policy.preferred_context_format,
            allowed_context_formats=tuple(policy.allowed_context_formats),
            configured_providers=configured_providers,
            primary_provider=configured_providers[0] if configured_providers else None,
        )

    def _build_db_prompt_record(self, prompt) -> AIPromptOperatorReadModel:
        policy = get_prompt_task_policy(prompt.task)
        return AIPromptOperatorReadModel(
            id=int(prompt.id),
            name=prompt.name,
            capability=None if policy is None else policy.capability,
            task=prompt.task,
            version=int(prompt.version),
            editable=False if policy is None else bool(policy.editable),
            source="db",
            is_active=bool(prompt.is_active),
            template=prompt.template,
            vars_json=prompt.vars_json,
            schema_contract=None if policy is None else freeze_json_value(policy.schema_contract),
            style_profile=prompt_style_profile(dict(prompt.vars_json or {})),
            updated_at=prompt.updated_at,
        )

    def _build_builtin_prompt_record(self, prompt) -> AIPromptOperatorReadModel:
        return AIPromptOperatorReadModel(
            id=None,
            name=prompt.name,
            capability=prompt.capability,
            task=prompt.task,
            version=int(prompt.version),
            editable=bool(prompt.editable),
            source=prompt.source,
            is_active=True,
            template=prompt.template,
            vars_json=freeze_json_value(dict(prompt.vars_json)),
            schema_contract=freeze_json_value(prompt.schema_contract),
            style_profile=prompt.style_profile,
            updated_at=None,
        )

    def _prompt_matches(
        self,
        prompt: AIPromptOperatorReadModel,
        *,
        name: str | None,
        capability: AICapability | None,
        task: str | None,
        editable: bool | None,
    ) -> bool:
        if name is not None and prompt.name != name:
            return False
        if capability is not None and prompt.capability is not capability:
            return False
        if task is not None and prompt.task != task:
            return False
        if editable is not None and bool(prompt.editable) is not bool(editable):
            return False
        return True


__all__ = [
    "AIOperatorQueryService",
    "AuditLogQueryService",
    "EventRegistryQueryService",
    "RouteQueryService",
    "TopologyDraftQueryService",
    "TopologyObservabilityQueryService",
    "TopologyQueryService",
    "observability_overview_payload",
    "route_snapshot_payload_from_read_model",
    "topology_graph_payload",
    "topology_snapshot_payload",
]
