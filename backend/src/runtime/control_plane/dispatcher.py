from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.apps.control_plane.contracts import (
    EventConsumerSnapshot,
    EventDefinitionSnapshot,
    EventRouteSnapshot,
    TopologySnapshot,
)
from src.apps.control_plane.enums import EventRouteScope, EventRouteStatus
from src.runtime.streams.types import IrisEvent


class RouteDeliveryPublisher(Protocol):
    async def publish(
        self,
        *,
        route: EventRouteSnapshot,
        consumer: EventConsumerSnapshot,
        event: IrisEvent,
        shadow: bool,
    ) -> None: ...


@dataclass(slots=True, frozen=True)
class RouteDecision:
    route: EventRouteSnapshot
    consumer: EventConsumerSnapshot
    deliver: bool
    shadow: bool
    reason: str


@dataclass(slots=True, frozen=True)
class DispatchReport:
    event_id: str
    event_type: str
    version_number: int
    decisions: tuple[RouteDecision, ...]

    @property
    def delivered_count(self) -> int:
        return sum(1 for decision in self.decisions if decision.deliver)

    @property
    def shadow_count(self) -> int:
        return sum(1 for decision in self.decisions if decision.shadow)

    @property
    def skipped_count(self) -> int:
        return sum(1 for decision in self.decisions if not decision.deliver)


class InMemoryRouteThrottle:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, int], int] = {}

    async def allow(self, route: EventRouteSnapshot, event: IrisEvent) -> bool:
        if route.throttle.limit is None or route.throttle.limit <= 0:
            return True
        window_seconds = max(int(route.throttle.window_seconds), 1)
        bucket = int(event.occurred_at.timestamp()) // window_seconds
        key = (route.route_key, bucket)
        current = self._counters.get(key, 0)
        if current >= int(route.throttle.limit):
            return False
        self._counters[key] = current + 1
        self._prune(bucket=bucket, route_key=route.route_key)
        return True

    def _prune(self, *, bucket: int, route_key: str) -> None:
        expired = [
            key
            for key in self._counters
            if key[0] == route_key and key[1] < bucket - 2
        ]
        for key in expired:
            self._counters.pop(key, None)


@dataclass(slots=True)
class DispatchCounter:
    evaluated: int = 0
    delivered: int = 0
    shadow: int = 0
    skipped: int = 0
    last_delivered_at: datetime | None = None


class InMemoryDispatchTracker:
    def __init__(self) -> None:
        self._route_counters: dict[str, DispatchCounter] = defaultdict(DispatchCounter)

    def record(self, event: IrisEvent, decisions: tuple[RouteDecision, ...]) -> None:
        for decision in decisions:
            counter = self._route_counters[decision.route.route_key]
            counter.evaluated += 1
            if decision.deliver:
                counter.delivered += 1
                counter.last_delivered_at = event.occurred_at
            else:
                counter.skipped += 1
            if decision.shadow:
                counter.shadow += 1

    def snapshot(self) -> dict[str, DispatchCounter]:
        return dict(self._route_counters)


class TopologyRouteEvaluator:
    def __init__(self, *, environment: str = "*", throttle: InMemoryRouteThrottle | None = None) -> None:
        self._environment = environment
        self._throttle = throttle or InMemoryRouteThrottle()

    async def evaluate(self, *, event: IrisEvent, snapshot: TopologySnapshot) -> tuple[RouteDecision, ...]:
        event_definition = snapshot.events.get(event.event_type)
        if event_definition is None:
            return ()

        decisions: list[RouteDecision] = []
        routes = sorted(snapshot.iter_routes(event.event_type), key=lambda route: route.priority)
        for route in routes:
            consumer = snapshot.consumers.get(route.consumer_key)
            if consumer is None:
                decisions.append(
                    RouteDecision(
                        route=route,
                        consumer=EventConsumerSnapshot(
                            consumer_key=route.consumer_key,
                            delivery_stream="",
                            compatible_event_types=(),
                            supports_shadow=False,
                        ),
                        deliver=False,
                        shadow=False,
                        reason="consumer_not_registered",
                    )
                )
                continue
            reason = await self._evaluate_reason(
                event=event,
                event_definition=event_definition,
                route=route,
                consumer=consumer,
                snapshot=snapshot,
            )
            decisions.append(
                RouteDecision(
                    route=route,
                    consumer=consumer,
                    deliver=reason == "deliver",
                    shadow=self._is_shadow(route),
                    reason=reason,
                )
            )
        return tuple(decisions)

    async def _evaluate_reason(
        self,
        *,
        event: IrisEvent,
        event_definition: EventDefinitionSnapshot,
        route: EventRouteSnapshot,
        consumer: EventConsumerSnapshot,
        snapshot: TopologySnapshot,
    ) -> str:
        if event.event_type not in set(consumer.compatible_event_types):
            return "incompatible_consumer"
        if not self._matches_environment(route):
            return "environment_mismatch"
        if not self._matches_scope(route=route, event=event, event_definition=event_definition, snapshot=snapshot):
            return "scope_mismatch"
        if not self._matches_filters(route=route, event=event, snapshot=snapshot):
            return "filter_mismatch"
        if route.status == EventRouteStatus.MUTED:
            return "muted"
        if route.status == EventRouteStatus.PAUSED:
            return "paused"
        if route.status == EventRouteStatus.DISABLED:
            return "disabled"
        if self._is_shadow(route) and (not consumer.supports_shadow or route.shadow.observe_only):
            return "shadow_observe_only"
        if route.status == EventRouteStatus.THROTTLED or route.throttle.limit is not None:
            allowed = await self._throttle.allow(route, event)
            if not allowed:
                return "throttled"
        return "deliver"

    def _matches_environment(self, route: EventRouteSnapshot) -> bool:
        return route.environment in {"*", self._environment}

    def _matches_scope(
        self,
        *,
        route: EventRouteSnapshot,
        event: IrisEvent,
        event_definition: EventDefinitionSnapshot,
        snapshot: TopologySnapshot,
    ) -> bool:
        if route.scope_type == EventRouteScope.GLOBAL:
            return True
        if route.scope_type == EventRouteScope.DOMAIN:
            return (route.scope_value or "").lower() == event_definition.domain.lower()
        if route.scope_type == EventRouteScope.SYMBOL:
            return (route.scope_value or "").upper() == (self._resolve_symbol(event, snapshot) or "").upper()
        if route.scope_type == EventRouteScope.EXCHANGE:
            return (route.scope_value or "").lower() == (self._resolve_exchange(event, snapshot) or "").lower()
        if route.scope_type == EventRouteScope.TIMEFRAME:
            return str(route.scope_value or "") == str(event.timeframe)
        if route.scope_type == EventRouteScope.ENVIRONMENT:
            return (route.scope_value or "*") in {"*", self._environment}
        return False

    def _matches_filters(self, *, route: EventRouteSnapshot, event: IrisEvent, snapshot: TopologySnapshot) -> bool:
        if route.filters.symbol:
            symbol = self._resolve_symbol(event, snapshot)
            if symbol is None or symbol.upper() not in {value.upper() for value in route.filters.symbol}:
                return False
        if route.filters.timeframe and int(event.timeframe) not in set(route.filters.timeframe):
            return False
        if route.filters.exchange:
            exchange = self._resolve_exchange(event, snapshot)
            if exchange is None or exchange.lower() not in {value.lower() for value in route.filters.exchange}:
                return False
        if route.filters.confidence is not None:
            confidence = event.confidence
            if confidence is None or confidence < route.filters.confidence:
                return False
        if route.filters.metadata:
            event_metadata = self._resolve_metadata(event)
            for key, expected in route.filters.metadata.items():
                actual = event_metadata.get(key)
                if isinstance(expected, (list, tuple, set)):
                    if actual not in set(expected):
                        return False
                elif actual != expected:
                    return False
        return True

    def _resolve_symbol(self, event: IrisEvent, snapshot: TopologySnapshot) -> str | None:
        if event.symbol is not None:
            return event.symbol
        if event.coin_id > 0:
            return snapshot.coin_symbol_by_id.get(int(event.coin_id))
        return None

    def _resolve_exchange(self, event: IrisEvent, snapshot: TopologySnapshot) -> str | None:
        if event.exchange is not None:
            return event.exchange
        if event.coin_id > 0:
            return snapshot.coin_exchange_by_id.get(int(event.coin_id))
        return None

    def _resolve_metadata(self, event: IrisEvent) -> dict[str, object]:
        payload_metadata = dict(event.metadata)
        return payload_metadata

    def _is_shadow(self, route: EventRouteSnapshot) -> bool:
        return route.status == EventRouteStatus.SHADOW or route.shadow.enabled


class TopologyDispatcher:
    def __init__(
        self,
        *,
        snapshot: TopologySnapshot,
        publisher: RouteDeliveryPublisher,
        evaluator: TopologyRouteEvaluator | None = None,
        tracker: InMemoryDispatchTracker | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._publisher = publisher
        self._evaluator = evaluator or TopologyRouteEvaluator()
        self._tracker = tracker or InMemoryDispatchTracker()

    async def dispatch(self, event: IrisEvent) -> DispatchReport:
        decisions = await self._evaluator.evaluate(event=event, snapshot=self._snapshot)
        for decision in decisions:
            if not decision.deliver:
                continue
            await self._publisher.publish(
                route=decision.route,
                consumer=decision.consumer,
                event=event,
                shadow=decision.shadow,
            )
        self._tracker.record(event, decisions)
        return DispatchReport(
            event_id=event.event_id,
            event_type=event.event_type,
            version_number=int(self._snapshot.version_number),
            decisions=decisions,
        )

    @property
    def tracker(self) -> InMemoryDispatchTracker:
        return self._tracker


__all__ = [
    "DispatchReport",
    "InMemoryDispatchTracker",
    "InMemoryRouteThrottle",
    "RouteDecision",
    "RouteDeliveryPublisher",
    "TopologyDispatcher",
    "TopologyRouteEvaluator",
]
