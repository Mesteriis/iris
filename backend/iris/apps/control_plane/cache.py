import json
from collections.abc import Sequence
from datetime import datetime
from functools import lru_cache
from typing import Any, cast

from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from iris.apps.control_plane.contracts import (
    EventConsumerSnapshot,
    EventDefinitionSnapshot,
    EventRouteSnapshot,
    RouteFilters,
    RouteShadow,
    RouteThrottle,
    TopologySnapshot,
)
from iris.apps.control_plane.control_events import CONTROL_EVENT_TYPES
from iris.apps.control_plane.enums import EventRouteScope, EventRouteStatus
from iris.apps.control_plane.models import EventRoute, TopologyConfigVersion
from iris.apps.market_data.models import Coin
from iris.core.db.session import AsyncSessionLocal
from iris.core.settings import get_settings
from iris.runtime.streams.types import IrisEvent

settings = get_settings()
TOPOLOGY_CACHE_KEY = "iris:control_plane:topology:snapshot"
TOPOLOGY_CACHE_VERSION_KEY = "iris:control_plane:topology:version"
TOPOLOGY_CACHE_TTL_SECONDS = 300
type CoinIdentityRow = tuple[int, str, str | None]


@lru_cache(maxsize=1)
def get_async_topology_cache_client() -> AsyncRedis:
    return cast(AsyncRedis, AsyncRedis.from_url(settings.redis_url, decode_responses=True))


class TopologySnapshotLoader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal) -> None:
        self._session_factory = session_factory

    async def load(self) -> TopologySnapshot:
        async with self._session_factory() as session:
            version = await self._load_version(session)
            routes = await self._load_routes(session)
            coin_rows = (
                await session.execute(
                    select(Coin.id, Coin.symbol, Coin.source).where(Coin.deleted_at.is_(None))
                )
            ).tuples().all()
        return self._build_snapshot(version=version, routes=routes, coin_rows=coin_rows)

    async def _load_version(self, session: AsyncSession) -> TopologyConfigVersion:
        return (
            await session.execute(
                select(TopologyConfigVersion)
                .where(TopologyConfigVersion.status == "published")
                .order_by(TopologyConfigVersion.version_number.desc(), TopologyConfigVersion.id.desc())
                .limit(1)
            )
        ).scalar_one()

    async def _load_routes(self, session: AsyncSession) -> list[EventRoute]:
        return list(
            (
                await session.execute(
                    select(EventRoute)
                    .options(joinedload(EventRoute.event_definition), joinedload(EventRoute.consumer))
                    .order_by(EventRoute.id.asc())
                )
            ).scalars().unique().all()
        )

    def _build_snapshot(
        self,
        *,
        version: TopologyConfigVersion,
        routes: list[EventRoute],
        coin_rows: Sequence[CoinIdentityRow],
    ) -> TopologySnapshot:
        event_snapshots: dict[str, EventDefinitionSnapshot] = {}
        consumer_snapshots: dict[str, EventConsumerSnapshot] = {}
        routes_by_event_type: dict[str, list[EventRouteSnapshot]] = {}
        for route in routes:
            if route.event_definition is None or route.consumer is None:
                raise ValueError(f"Event route {route.route_key!r} is missing required related records.")
            event_type = route.event_definition.event_type
            consumer_key = route.consumer.consumer_key
            event_snapshots[event_type] = EventDefinitionSnapshot(
                event_type=event_type,
                domain=route.event_definition.domain,
                is_control_event=bool(route.event_definition.is_control_event),
            )
            consumer_snapshots[consumer_key] = EventConsumerSnapshot(
                consumer_key=consumer_key,
                delivery_stream=route.consumer.delivery_stream,
                compatible_event_types=tuple(route.consumer.compatible_event_types_json or []),
                supports_shadow=bool(route.consumer.supports_shadow),
                settings=dict(route.consumer.settings_json or {}),
            )
            routes_by_event_type.setdefault(event_type, []).append(
                EventRouteSnapshot(
                    route_key=route.route_key,
                    event_type=event_type,
                    consumer_key=consumer_key,
                    status=EventRouteStatus(route.status),
                    scope_type=EventRouteScope(route.scope_type),
                    scope_value=route.scope_value,
                    environment=route.environment,
                    filters=RouteFilters.from_json(route.filters_json),
                    throttle=RouteThrottle.from_json(route.throttle_config_json),
                    shadow=RouteShadow.from_json(route.shadow_config_json),
                    notes=route.notes,
                    priority=int(route.priority),
                    system_managed=bool(route.system_managed),
                )
            )
        return TopologySnapshot(
            version_number=int(version.version_number),
            created_at=version.created_at,
            events=event_snapshots,
            consumers=consumer_snapshots,
            routes_by_event_type={key: tuple(value) for key, value in routes_by_event_type.items()},
            coin_symbol_by_id={int(coin_id): str(symbol) for coin_id, symbol, _source in coin_rows},
            coin_exchange_by_id={
                int(coin_id): str(source or "")
                for coin_id, _symbol, source in coin_rows
            },
        )


class TopologySnapshotCodec:
    @staticmethod
    def dump(snapshot: TopologySnapshot) -> str:
        payload = {
            "version_number": int(snapshot.version_number),
            "created_at": snapshot.created_at.isoformat() if snapshot.created_at is not None else None,
            "events": {
                key: {
                    "event_type": value.event_type,
                    "domain": value.domain,
                    "is_control_event": value.is_control_event,
                }
                for key, value in snapshot.events.items()
            },
            "consumers": {
                key: {
                    "consumer_key": value.consumer_key,
                    "delivery_stream": value.delivery_stream,
                    "compatible_event_types": list(value.compatible_event_types),
                    "supports_shadow": value.supports_shadow,
                    "settings": dict(value.settings),
                }
                for key, value in snapshot.consumers.items()
            },
            "routes_by_event_type": {
                event_type: [
                    {
                        "route_key": route.route_key,
                        "event_type": route.event_type,
                        "consumer_key": route.consumer_key,
                        "status": route.status.value,
                        "scope_type": route.scope_type.value,
                        "scope_value": route.scope_value,
                        "environment": route.environment,
                        "filters": route.filters.to_json(),
                        "throttle": route.throttle.to_json(),
                        "shadow": route.shadow.to_json(),
                        "notes": route.notes,
                        "priority": route.priority,
                        "system_managed": route.system_managed,
                    }
                    for route in routes
                ]
                for event_type, routes in snapshot.routes_by_event_type.items()
            },
            "coin_symbol_by_id": {str(key): value for key, value in snapshot.coin_symbol_by_id.items()},
            "coin_exchange_by_id": {str(key): value for key, value in snapshot.coin_exchange_by_id.items()},
        }
        return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def load(raw: str) -> TopologySnapshot:
        payload = json.loads(raw)
        return TopologySnapshot(
            version_number=int(payload["version_number"]),
            created_at=datetime.fromisoformat(payload["created_at"]) if payload.get("created_at") else None,
            events={
                key: EventDefinitionSnapshot(
                    event_type=value["event_type"],
                    domain=value["domain"],
                    is_control_event=bool(value.get("is_control_event", False)),
                )
                for key, value in dict(payload.get("events") or {}).items()
            },
            consumers={
                key: EventConsumerSnapshot(
                    consumer_key=value["consumer_key"],
                    delivery_stream=value["delivery_stream"],
                    compatible_event_types=tuple(value.get("compatible_event_types") or []),
                    supports_shadow=bool(value.get("supports_shadow", False)),
                    settings=dict(value.get("settings") or {}),
                )
                for key, value in dict(payload.get("consumers") or {}).items()
            },
            routes_by_event_type={
                event_type: tuple(
                    EventRouteSnapshot(
                        route_key=route["route_key"],
                        event_type=route["event_type"],
                        consumer_key=route["consumer_key"],
                        status=EventRouteStatus(route["status"]),
                        scope_type=EventRouteScope(route["scope_type"]),
                        scope_value=route.get("scope_value"),
                        environment=route.get("environment", "*"),
                        filters=RouteFilters.from_json(route.get("filters")),
                        throttle=RouteThrottle.from_json(route.get("throttle")),
                        shadow=RouteShadow.from_json(route.get("shadow")),
                        notes=route.get("notes"),
                        priority=int(route.get("priority", 100)),
                        system_managed=bool(route.get("system_managed", False)),
                    )
                    for route in routes
                )
                for event_type, routes in dict(payload.get("routes_by_event_type") or {}).items()
            },
            coin_symbol_by_id={int(key): str(value) for key, value in dict(payload.get("coin_symbol_by_id") or {}).items()},
            coin_exchange_by_id={
                int(key): str(value) for key, value in dict(payload.get("coin_exchange_by_id") or {}).items()
            },
        )


class TopologyCacheManager:
    def __init__(
        self,
        *,
        loader: TopologySnapshotLoader | None = None,
        cache_client: AsyncRedis | None = None,
    ) -> None:
        self._loader = loader or TopologySnapshotLoader()
        self._cache_client = cache_client or get_async_topology_cache_client()
        self._local_snapshot: TopologySnapshot | None = None

    async def get_snapshot(self, *, force_refresh: bool = False) -> TopologySnapshot:
        if self._local_snapshot is not None and not force_refresh:
            return self._local_snapshot
        if not force_refresh:
            cached = await self._cache_client.get(TOPOLOGY_CACHE_KEY)
            if cached:
                self._local_snapshot = TopologySnapshotCodec.load(cached)
                return self._local_snapshot
        snapshot = await self._loader.load()
        await self._cache_client.set(TOPOLOGY_CACHE_KEY, TopologySnapshotCodec.dump(snapshot), ex=TOPOLOGY_CACHE_TTL_SECONDS)
        await self._cache_client.set(TOPOLOGY_CACHE_VERSION_KEY, str(snapshot.version_number), ex=TOPOLOGY_CACHE_TTL_SECONDS)
        self._local_snapshot = snapshot
        return snapshot

    async def invalidate(self) -> None:
        self._local_snapshot = None
        await self._cache_client.delete(TOPOLOGY_CACHE_KEY)
        await self._cache_client.delete(TOPOLOGY_CACHE_VERSION_KEY)

    async def refresh_from_control_event(self, event: IrisEvent) -> TopologySnapshot | None:
        if event.event_type not in CONTROL_EVENT_TYPES:
            return None
        return await self.get_snapshot(force_refresh=True)


__all__ = [
    "TOPOLOGY_CACHE_KEY",
    "TOPOLOGY_CACHE_TTL_SECONDS",
    "TOPOLOGY_CACHE_VERSION_KEY",
    "TopologyCacheManager",
    "TopologySnapshotCodec",
    "TopologySnapshotLoader",
    "get_async_topology_cache_client",
]
