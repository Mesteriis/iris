from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.apps.control_plane.contracts import (
    EventConsumerSnapshot,
    EventDefinitionSnapshot,
    EventRouteSnapshot,
    RouteFilters,
    RouteShadow,
    RouteThrottle,
    TopologySnapshot,
)
from src.apps.control_plane.enums import EventRouteScope, EventRouteStatus
from src.runtime.control_plane.dispatcher import InMemoryRouteThrottle, RouteDeliveryPublisher, TopologyDispatcher, TopologyRouteEvaluator
from src.runtime.streams.types import IrisEvent


class RecordingPublisher(RouteDeliveryPublisher):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bool]] = []

    async def publish(self, *, route, consumer, event, shadow) -> None:
        self.calls.append((route.route_key, consumer.consumer_key, shadow))


def _event(
    *,
    event_type: str = "signal_created",
    coin_id: int = 1,
    timeframe: int = 15,
    payload: dict[str, object] | None = None,
) -> IrisEvent:
    return IrisEvent(
        stream_id="1-0",
        event_type=event_type,
        coin_id=coin_id,
        timeframe=timeframe,
        timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
        payload=payload or {},
    )


def _snapshot(*routes: EventRouteSnapshot, supports_shadow: bool = False) -> TopologySnapshot:
    return TopologySnapshot(
        version_number=1,
        created_at=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
        events={
            "signal_created": EventDefinitionSnapshot(event_type="signal_created", domain="signals"),
            "market_regime_changed": EventDefinitionSnapshot(event_type="market_regime_changed", domain="indicators"),
        },
        consumers={
            "hypothesis_workers": EventConsumerSnapshot(
                consumer_key="hypothesis_workers",
                delivery_stream="iris:deliveries:hypothesis_workers",
                compatible_event_types=("signal_created", "market_regime_changed"),
                supports_shadow=supports_shadow,
            ),
            "portfolio_workers": EventConsumerSnapshot(
                consumer_key="portfolio_workers",
                delivery_stream="iris:deliveries:portfolio_workers",
                compatible_event_types=("market_regime_changed",),
            ),
        },
        routes_by_event_type={
            "signal_created": tuple(route for route in routes if route.event_type == "signal_created"),
            "market_regime_changed": tuple(route for route in routes if route.event_type == "market_regime_changed"),
        },
        coin_symbol_by_id={1: "BTCUSD", 2: "ETHUSD"},
        coin_exchange_by_id={1: "binance", 2: "coinbase"},
    )


@pytest.mark.asyncio
async def test_dispatcher_delivers_active_route() -> None:
    route = EventRouteSnapshot(
        route_key="signal_created:hypothesis_workers:global:*:*",
        event_type="signal_created",
        consumer_key="hypothesis_workers",
        status=EventRouteStatus.ACTIVE,
        scope_type=EventRouteScope.GLOBAL,
    )
    publisher = RecordingPublisher()
    dispatcher = TopologyDispatcher(snapshot=_snapshot(route), publisher=publisher)

    report = await dispatcher.dispatch(_event())

    assert report.delivered_count == 1
    assert publisher.calls == [(route.route_key, "hypothesis_workers", False)]


@pytest.mark.asyncio
async def test_dispatcher_applies_filters_and_scope() -> None:
    route = EventRouteSnapshot(
        route_key="signal_created:hypothesis_workers:symbol:BTCUSD:*",
        event_type="signal_created",
        consumer_key="hypothesis_workers",
        status=EventRouteStatus.ACTIVE,
        scope_type=EventRouteScope.SYMBOL,
        scope_value="BTCUSD",
        filters=RouteFilters(
            symbol=("BTCUSD",),
            timeframe=(15,),
            exchange=("binance",),
            confidence=0.7,
            metadata={"source": "fusion"},
        ),
    )
    publisher = RecordingPublisher()
    dispatcher = TopologyDispatcher(snapshot=_snapshot(route), publisher=publisher)

    matching = await dispatcher.dispatch(
        _event(
            payload={
                "confidence": 0.82,
                "exchange": "binance",
                "metadata": {"source": "fusion"},
            }
        )
    )
    non_matching = await dispatcher.dispatch(
        _event(
            payload={
                "confidence": 0.4,
                "exchange": "binance",
                "metadata": {"source": "fusion"},
            }
        )
    )

    assert matching.delivered_count == 1
    assert non_matching.delivered_count == 0
    assert non_matching.decisions[0].reason == "filter_mismatch"


@pytest.mark.asyncio
async def test_dispatcher_respects_muted_paused_and_disabled_routes() -> None:
    muted = EventRouteSnapshot(
        route_key="market_regime_changed:portfolio_workers:global:*:*",
        event_type="market_regime_changed",
        consumer_key="portfolio_workers",
        status=EventRouteStatus.MUTED,
        scope_type=EventRouteScope.GLOBAL,
    )
    paused = EventRouteSnapshot(
        route_key="signal_created:hypothesis_workers:global:*:*",
        event_type="signal_created",
        consumer_key="hypothesis_workers",
        status=EventRouteStatus.PAUSED,
        scope_type=EventRouteScope.GLOBAL,
    )
    publisher = RecordingPublisher()
    dispatcher = TopologyDispatcher(snapshot=_snapshot(muted, paused), publisher=publisher)

    muted_report = await dispatcher.dispatch(_event(event_type="market_regime_changed"))
    paused_report = await dispatcher.dispatch(_event())

    assert muted_report.decisions[0].reason == "muted"
    assert paused_report.decisions[0].reason == "paused"
    assert publisher.calls == []


@pytest.mark.asyncio
async def test_dispatcher_shadow_mode_observes_without_delivery_when_consumer_cannot_shadow() -> None:
    route = EventRouteSnapshot(
        route_key="signal_created:hypothesis_workers:global:*:*",
        event_type="signal_created",
        consumer_key="hypothesis_workers",
        status=EventRouteStatus.SHADOW,
        scope_type=EventRouteScope.GLOBAL,
        shadow=RouteShadow(enabled=True, observe_only=True),
    )
    publisher = RecordingPublisher()
    dispatcher = TopologyDispatcher(snapshot=_snapshot(route, supports_shadow=False), publisher=publisher)

    report = await dispatcher.dispatch(_event())

    assert report.delivered_count == 0
    assert report.shadow_count == 1
    assert report.decisions[0].reason == "shadow_observe_only"


@pytest.mark.asyncio
async def test_dispatcher_throttles_routes() -> None:
    route = EventRouteSnapshot(
        route_key="signal_created:hypothesis_workers:global:*:*",
        event_type="signal_created",
        consumer_key="hypothesis_workers",
        status=EventRouteStatus.THROTTLED,
        scope_type=EventRouteScope.GLOBAL,
        throttle=RouteThrottle(limit=1, window_seconds=60),
    )
    publisher = RecordingPublisher()
    evaluator = TopologyRouteEvaluator(throttle=InMemoryRouteThrottle())
    dispatcher = TopologyDispatcher(snapshot=_snapshot(route), publisher=publisher, evaluator=evaluator)

    first = await dispatcher.dispatch(_event())
    second = await dispatcher.dispatch(_event())

    assert first.delivered_count == 1
    assert second.delivered_count == 0
    assert second.decisions[0].reason == "throttled"
    assert publisher.calls == [(route.route_key, "hypothesis_workers", False)]
