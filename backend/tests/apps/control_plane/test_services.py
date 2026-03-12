from __future__ import annotations

import pytest
from sqlalchemy import select

from src.apps.control_plane.contracts import (
    AuditActor,
    DraftChangeCommand,
    DraftCreateCommand,
    RouteMutationCommand,
    RouteStatusChangeCommand,
    build_route_key,
)
from src.apps.control_plane.enums import (
    EventRouteScope,
    EventRouteStatus,
    TopologyAccessMode,
    TopologyDraftChangeType,
)
from src.apps.control_plane.exceptions import EventRouteCompatibilityError
from src.apps.control_plane.models import EventRoute, EventRouteAuditLog
from src.apps.control_plane.services import EventRegistryService, RouteManagementService, TopologyDraftService, TopologyService


@pytest.mark.asyncio
async def test_event_registry_lists_compatible_consumers(async_db_session, isolated_control_plane_state) -> None:
    service = EventRegistryService(async_db_session)

    consumers = await service.list_compatible_consumers("news_item_normalized")

    assert [consumer.consumer_key for consumer in consumers] == ["news_correlation_workers"]


@pytest.mark.asyncio
async def test_route_management_creates_scoped_route_and_audit(async_db_session, isolated_control_plane_state) -> None:
    service = RouteManagementService(async_db_session)
    route = await service.create_route(
        RouteMutationCommand(
            event_type="signal_created",
            consumer_key="hypothesis_workers",
            status=EventRouteStatus.SHADOW,
            scope_type=EventRouteScope.SYMBOL,
            scope_value="BTCUSD",
            notes="Shadow BTC hypothesis fan-out",
            priority=150,
        ),
        actor=AuditActor(actor="test-suite"),
    )

    assert route.route_key == build_route_key(
        "signal_created",
        "hypothesis_workers",
        EventRouteScope.SYMBOL,
        "BTCUSD",
        "*",
    )
    assert route.status == EventRouteStatus.SHADOW.value

    audit_rows = (
        await async_db_session.execute(
            select(EventRouteAuditLog)
            .where(EventRouteAuditLog.route_key_snapshot == route.route_key)
            .order_by(EventRouteAuditLog.id.asc())
        )
    ).scalars().all()
    assert [row.action for row in audit_rows][-1] == "created"


@pytest.mark.asyncio
async def test_route_management_rejects_incompatible_route(async_db_session, isolated_control_plane_state) -> None:
    service = RouteManagementService(async_db_session)

    with pytest.raises(EventRouteCompatibilityError):
        await service.create_route(
            RouteMutationCommand(
                event_type="news_item_normalized",
                consumer_key="decision_workers",
                scope_type=EventRouteScope.SYMBOL,
                scope_value="BTCUSD",
            ),
            actor=AuditActor(actor="test-suite"),
        )


@pytest.mark.asyncio
async def test_route_status_change_persists_and_audits(async_db_session, isolated_control_plane_state) -> None:
    service = RouteManagementService(async_db_session)
    route_key = build_route_key(
        "market_regime_changed",
        "portfolio_workers",
        EventRouteScope.GLOBAL,
        None,
        "*",
    )

    updated = await service.change_status(
        RouteStatusChangeCommand(
            route_key=route_key,
            status=EventRouteStatus.MUTED,
            notes="Muted during portfolio replay",
        ),
        actor=AuditActor(actor="ops", reason="portfolio_replay"),
    )

    assert updated.status == EventRouteStatus.MUTED.value
    current = (
        await async_db_session.execute(select(EventRoute).where(EventRoute.route_key == route_key).limit(1))
    ).scalar_one()
    assert current.notes == "Muted during portfolio replay"

    audit_rows = (
        await async_db_session.execute(
            select(EventRouteAuditLog)
            .where(EventRouteAuditLog.route_key_snapshot == route_key)
            .order_by(EventRouteAuditLog.id.asc())
        )
    ).scalars().all()
    assert [row.action for row in audit_rows][-1] == "status_changed"


@pytest.mark.asyncio
async def test_topology_draft_preview_accumulates_changes(async_db_session, isolated_control_plane_state) -> None:
    draft_service = TopologyDraftService(async_db_session)
    topology_service = TopologyService(async_db_session)
    route_key = build_route_key(
        "market_regime_changed",
        "portfolio_workers",
        EventRouteScope.GLOBAL,
        None,
        "*",
    )

    draft = await draft_service.create_draft(
        DraftCreateCommand(
            name="Portfolio replay sandbox",
            description="Draft muted portfolio regime route plus symbol shadow route.",
            access_mode=TopologyAccessMode.CONTROL,
            created_by="ops",
        )
    )
    await draft_service.add_change(
        int(draft.id),
        DraftChangeCommand(
            change_type=TopologyDraftChangeType.ROUTE_STATUS_CHANGED,
            target_route_key=route_key,
            payload={"status": EventRouteStatus.PAUSED.value, "notes": "Paused in draft"},
            created_by="ops",
        ),
    )
    await draft_service.add_change(
        int(draft.id),
        DraftChangeCommand(
            change_type=TopologyDraftChangeType.ROUTE_CREATED,
            payload={
                "event_type": "signal_created",
                "consumer_key": "hypothesis_workers",
                "status": EventRouteStatus.SHADOW.value,
                "scope_type": EventRouteScope.SYMBOL.value,
                "scope_value": "ETHUSD",
                "environment": "*",
                "notes": "Shadow only for ETH",
                "priority": 120,
            },
            created_by="ops",
        ),
    )

    diff = await draft_service.preview_diff(int(draft.id))
    snapshot = await topology_service.build_snapshot()

    assert snapshot["version_number"] == 1
    assert {item.change_type for item in diff} == {
        TopologyDraftChangeType.ROUTE_STATUS_CHANGED,
        TopologyDraftChangeType.ROUTE_CREATED,
    }
    created_items = [item for item in diff if item.change_type == TopologyDraftChangeType.ROUTE_CREATED]
    assert created_items[0].after["consumer_key"] == "hypothesis_workers"
    assert created_items[0].after["scope_type"] == EventRouteScope.SYMBOL.value
