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
from src.apps.control_plane.control_events import CONTROL_CACHE_INVALIDATED, CONTROL_TOPOLOGY_PUBLISHED
from src.apps.control_plane.enums import (
    EventRouteScope,
    EventRouteStatus,
    TopologyAccessMode,
    TopologyDraftChangeType,
)
from src.apps.control_plane.exceptions import EventRouteCompatibilityError
from src.apps.control_plane.models import EventRoute, EventRouteAuditLog, TopologyConfigVersion
from src.apps.control_plane.services import (
    EventRegistryService,
    RouteManagementService,
    TopologyDraftService,
    TopologyService,
)
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_event_registry_lists_compatible_consumers(async_db_session, isolated_control_plane_state) -> None:
    service = EventRegistryService(async_db_session)

    consumers = await service.list_compatible_consumers("news_item_normalized")

    assert [consumer.consumer_key for consumer in consumers] == ["news_correlation_workers"]


@pytest.mark.asyncio
async def test_route_management_creates_scoped_route_and_audit(async_db_session, isolated_control_plane_state) -> None:
    async with SessionUnitOfWork(async_db_session) as uow:
        service = RouteManagementService(uow)
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
        route_key = route.route_key
        await uow.commit()

    assert route_key == build_route_key(
        "signal_created",
        "hypothesis_workers",
        EventRouteScope.SYMBOL,
        "BTCUSD",
        "*",
    )

    audit_rows = (
        (
            await async_db_session.execute(
                select(EventRouteAuditLog)
                .where(EventRouteAuditLog.route_key_snapshot == route_key)
                .order_by(EventRouteAuditLog.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert [row.action for row in audit_rows][-1] == "created"


@pytest.mark.asyncio
async def test_route_management_rejects_incompatible_route(async_db_session, isolated_control_plane_state) -> None:
    with pytest.raises(EventRouteCompatibilityError):
        async with SessionUnitOfWork(async_db_session) as uow:
            service = RouteManagementService(uow)
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
    route_key = build_route_key(
        "market_regime_changed",
        "portfolio_workers",
        EventRouteScope.GLOBAL,
        None,
        "*",
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        service = RouteManagementService(uow)
        updated = await service.change_status(
            RouteStatusChangeCommand(
                route_key=route_key,
                status=EventRouteStatus.MUTED,
                notes="Muted during portfolio replay",
            ),
            actor=AuditActor(actor="ops", reason="portfolio_replay"),
        )
        updated_route_key = updated.route_key
        await uow.commit()

    assert updated_route_key == route_key
    current = (
        await async_db_session.execute(select(EventRoute).where(EventRoute.route_key == route_key).limit(1))
    ).scalar_one()
    assert current.status == EventRouteStatus.MUTED.value
    assert current.notes == "Muted during portfolio replay"

    audit_rows = (
        (
            await async_db_session.execute(
                select(EventRouteAuditLog)
                .where(EventRouteAuditLog.route_key_snapshot == route_key)
                .order_by(EventRouteAuditLog.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert [row.action for row in audit_rows][-1] == "status_changed"


@pytest.mark.asyncio
async def test_topology_draft_preview_accumulates_changes(async_db_session, isolated_control_plane_state) -> None:
    topology_service = TopologyService(async_db_session)
    route_key = build_route_key(
        "market_regime_changed",
        "portfolio_workers",
        EventRouteScope.GLOBAL,
        None,
        "*",
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        draft_service = TopologyDraftService(uow)
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


@pytest.mark.asyncio
async def test_topology_draft_apply_publishes_new_version_and_route_changes(
    async_db_session,
    isolated_control_plane_state,
    monkeypatch,
) -> None:
    route_key = build_route_key(
        "market_regime_changed",
        "portfolio_workers",
        EventRouteScope.GLOBAL,
        None,
        "*",
    )
    published_events: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        "src.apps.control_plane.services.publish_control_event",
        lambda event_type, payload: published_events.append((event_type, dict(payload))),
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        draft_service = TopologyDraftService(uow)
        draft = await draft_service.create_draft(
            DraftCreateCommand(
                name="Topology publish",
                description="Pause portfolio route and add ETH shadow route.",
                access_mode=TopologyAccessMode.CONTROL,
                created_by="ops",
            )
        )
        await draft_service.add_change(
            int(draft.id),
            DraftChangeCommand(
                change_type=TopologyDraftChangeType.ROUTE_STATUS_CHANGED,
                target_route_key=route_key,
                payload={"status": EventRouteStatus.PAUSED.value, "notes": "Paused in publish"},
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
                    "notes": "Applied ETH route",
                    "priority": 130,
                },
                created_by="ops",
            ),
        )
        applied_draft, version = await draft_service.apply_draft(int(draft.id), actor=AuditActor(actor="ops"))
        draft_id = int(draft.id)
        version_id = int(version.id)
        version_number = int(version.version_number)
        await uow.commit()

    persisted_draft = await async_db_session.get(type(applied_draft), draft_id)
    assert persisted_draft is not None
    assert persisted_draft.status == "applied"
    assert version_number == 2

    refreshed_route = (
        await async_db_session.execute(select(EventRoute).where(EventRoute.route_key == route_key).limit(1))
    ).scalar_one()
    assert refreshed_route.status == EventRouteStatus.PAUSED.value

    created_route_key = build_route_key(
        "signal_created",
        "hypothesis_workers",
        EventRouteScope.SYMBOL,
        "ETHUSD",
        "*",
    )
    created_route = (
        await async_db_session.execute(select(EventRoute).where(EventRoute.route_key == created_route_key).limit(1))
    ).scalar_one()
    assert created_route.status == EventRouteStatus.SHADOW.value

    stored_version = (
        await async_db_session.execute(
            select(TopologyConfigVersion).where(TopologyConfigVersion.version_number == version_number).limit(1)
        )
    ).scalar_one()
    assert int(stored_version.id) == version_id
    assert stored_version.snapshot_json["version_number"] == version_number
    assert any(route["route_key"] == created_route_key for route in stored_version.snapshot_json["routes"])

    draft_audit_rows = (
        (
            await async_db_session.execute(
                select(EventRouteAuditLog)
                .where(EventRouteAuditLog.draft_id == draft_id)
                .order_by(EventRouteAuditLog.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert {row.action for row in draft_audit_rows} == {"status_changed", "created"}
    assert {int(row.topology_version_id) for row in draft_audit_rows if row.topology_version_id is not None} == {
        version_id
    }
    assert published_events == [
        (
            CONTROL_TOPOLOGY_PUBLISHED,
            {"draft_id": draft_id, "version_number": version_number, "actor": "ops"},
        ),
        (
            CONTROL_CACHE_INVALIDATED,
            {"reason": "topology_published", "draft_id": draft_id, "version_number": version_number, "actor": "ops"},
        ),
    ]


@pytest.mark.asyncio
async def test_topology_draft_discard_marks_state_and_audits(async_db_session, isolated_control_plane_state) -> None:
    route_key = build_route_key(
        "market_regime_changed",
        "portfolio_workers",
        EventRouteScope.GLOBAL,
        None,
        "*",
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        draft_service = TopologyDraftService(uow)
        draft = await draft_service.create_draft(
            DraftCreateCommand(
                name="Discard me",
                description="Draft that should never publish.",
                access_mode=TopologyAccessMode.CONTROL,
                created_by="ops",
            )
        )
        await draft_service.add_change(
            int(draft.id),
            DraftChangeCommand(
                change_type=TopologyDraftChangeType.ROUTE_STATUS_CHANGED,
                target_route_key=route_key,
                payload={"status": EventRouteStatus.MUTED.value, "notes": "Muted only in draft"},
                created_by="ops",
            ),
        )
        discarded = await draft_service.discard_draft(int(draft.id), actor=AuditActor(actor="ops"))
        draft_id = int(draft.id)
        await uow.commit()

    persisted_draft = await async_db_session.get(type(discarded), draft_id)
    assert persisted_draft is not None
    assert persisted_draft.status == "discarded"
    persisted_route = (
        await async_db_session.execute(select(EventRoute).where(EventRoute.route_key == route_key).limit(1))
    ).scalar_one()
    assert persisted_route.status == EventRouteStatus.ACTIVE.value

    audit_rows = (
        (
            await async_db_session.execute(
                select(EventRouteAuditLog)
                .where(EventRouteAuditLog.draft_id == draft_id)
                .order_by(EventRouteAuditLog.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert [row.action for row in audit_rows] == ["draft_discarded"]


@pytest.mark.asyncio
async def test_topology_draft_preview_supports_route_update_and_delete(
    async_db_session,
    isolated_control_plane_state,
) -> None:
    existing_route_key = build_route_key(
        "market_regime_changed",
        "portfolio_workers",
        EventRouteScope.GLOBAL,
        None,
        "*",
    )
    delete_route_key = build_route_key(
        "decision_generated",
        "portfolio_workers",
        EventRouteScope.GLOBAL,
        None,
        "*",
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        draft_service = TopologyDraftService(uow)
        draft = await draft_service.create_draft(
            DraftCreateCommand(
                name="Update and delete preview",
                description="Preview route update and delete support.",
                access_mode=TopologyAccessMode.CONTROL,
                created_by="ops",
            )
        )
        await draft_service.add_change(
            int(draft.id),
            DraftChangeCommand(
                change_type=TopologyDraftChangeType.ROUTE_UPDATED,
                target_route_key=existing_route_key,
                payload={
                    "event_type": "market_regime_changed",
                    "consumer_key": "portfolio_workers",
                    "status": EventRouteStatus.THROTTLED.value,
                    "scope_type": EventRouteScope.SYMBOL.value,
                    "scope_value": "BTCUSD",
                    "environment": "development",
                    "priority": 25,
                    "notes": "Updated in draft",
                    "shadow": {"enabled": True, "observe_only": True, "sample_rate": 0.5},
                    "throttle": {"limit": 2, "window_seconds": 120},
                },
                created_by="ops",
            ),
        )
        await draft_service.add_change(
            int(draft.id),
            DraftChangeCommand(
                change_type=TopologyDraftChangeType.ROUTE_DELETED,
                target_route_key=delete_route_key,
                payload={},
                created_by="ops",
            ),
        )
        diff = await draft_service.preview_diff(int(draft.id))
    diff_by_type = {item.change_type: item for item in diff}

    updated = diff_by_type[TopologyDraftChangeType.ROUTE_UPDATED]
    assert updated.after["scope_type"] == EventRouteScope.SYMBOL.value
    assert updated.after["scope_value"] == "BTCUSD"
    assert updated.after["throttle"] == {"limit": 2, "window_seconds": 120}
    assert updated.after["shadow"] == {"enabled": True, "sample_rate": 0.5, "observe_only": True}

    deleted = diff_by_type[TopologyDraftChangeType.ROUTE_DELETED]
    assert deleted.route_key == delete_route_key
    assert deleted.before["route_key"] == delete_route_key
    assert deleted.after == {}


@pytest.mark.asyncio
async def test_topology_draft_apply_supports_route_update_and_delete(
    async_db_session,
    isolated_control_plane_state,
) -> None:
    existing_route_key = build_route_key(
        "market_regime_changed",
        "portfolio_workers",
        EventRouteScope.GLOBAL,
        None,
        "*",
    )
    delete_route_key = build_route_key(
        "decision_generated",
        "portfolio_workers",
        EventRouteScope.GLOBAL,
        None,
        "*",
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        draft_service = TopologyDraftService(uow)
        draft = await draft_service.create_draft(
            DraftCreateCommand(
                name="Apply update and delete",
                description="Publish route update and delete changes.",
                access_mode=TopologyAccessMode.CONTROL,
                created_by="ops",
            )
        )
        await draft_service.add_change(
            int(draft.id),
            DraftChangeCommand(
                change_type=TopologyDraftChangeType.ROUTE_UPDATED,
                target_route_key=existing_route_key,
                payload={
                    "event_type": "market_regime_changed",
                    "consumer_key": "portfolio_workers",
                    "status": EventRouteStatus.THROTTLED.value,
                    "scope_type": EventRouteScope.EXCHANGE.value,
                    "scope_value": "fixture",
                    "environment": "development",
                    "priority": 10,
                    "notes": "Updated through apply",
                    "shadow": {"enabled": True, "observe_only": True, "sample_rate": 0.25},
                    "throttle": {"limit": 1, "window_seconds": 300},
                },
                created_by="ops",
            ),
        )
        await draft_service.add_change(
            int(draft.id),
            DraftChangeCommand(
                change_type=TopologyDraftChangeType.ROUTE_DELETED,
                target_route_key=delete_route_key,
                payload={},
                created_by="ops",
            ),
        )
        applied_draft, version = await draft_service.apply_draft(int(draft.id), actor=AuditActor(actor="ops"))
        draft_id = int(draft.id)
        version_id = int(version.id)
        version_number = int(version.version_number)
        await uow.commit()

    persisted_draft = await async_db_session.get(type(applied_draft), draft_id)
    assert persisted_draft is not None
    assert persisted_draft.status == "applied"
    assert version_number == 2

    updated_route_key = build_route_key(
        "market_regime_changed",
        "portfolio_workers",
        EventRouteScope.EXCHANGE,
        "fixture",
        "development",
    )
    updated_route = (
        await async_db_session.execute(select(EventRoute).where(EventRoute.route_key == updated_route_key).limit(1))
    ).scalar_one()
    assert updated_route.status == EventRouteStatus.THROTTLED.value
    assert updated_route.scope_type == EventRouteScope.EXCHANGE.value
    assert updated_route.scope_value == "fixture"
    assert updated_route.environment == "development"
    assert updated_route.priority == 10
    assert updated_route.notes == "Updated through apply"
    assert updated_route.shadow_config_json == {"enabled": True, "sample_rate": 0.25, "observe_only": True}
    assert updated_route.throttle_config_json == {"limit": 1, "window_seconds": 300}

    deleted_route = (
        await async_db_session.execute(select(EventRoute).where(EventRoute.route_key == delete_route_key).limit(1))
    ).scalar_one_or_none()
    assert deleted_route is None
    original_route = (
        await async_db_session.execute(select(EventRoute).where(EventRoute.route_key == existing_route_key).limit(1))
    ).scalar_one_or_none()
    assert original_route is None

    audit_rows = (
        (
            await async_db_session.execute(
                select(EventRouteAuditLog)
                .where(EventRouteAuditLog.draft_id == int(draft.id))
                .order_by(EventRouteAuditLog.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert {row.action for row in audit_rows} == {"updated", "deleted"}
    assert {int(row.topology_version_id) for row in audit_rows if row.topology_version_id is not None} == {
        version_id
    }
