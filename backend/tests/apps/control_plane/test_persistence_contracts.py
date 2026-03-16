from dataclasses import FrozenInstanceError

import pytest
from src.apps.control_plane.contracts import AuditActor, DraftChangeCommand, DraftCreateCommand, RouteMutationCommand
from src.apps.control_plane.enums import EventRouteScope, EventRouteStatus, TopologyAccessMode, TopologyDraftChangeType
from src.apps.control_plane.query_services import EventRegistryQueryService, TopologyDraftQueryService
from src.apps.control_plane.services import RouteManagementService, TopologyDraftService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_control_plane_registry_query_returns_immutable_read_models(
    async_db_session,
    isolated_control_plane_state,
) -> None:
    items = await EventRegistryQueryService(async_db_session).list_event_definitions()

    assert items
    with pytest.raises(FrozenInstanceError):
        items[0].event_type = "changed"
    with pytest.raises(TypeError):
        items[0].payload_schema_json["shape"] = "other"


@pytest.mark.asyncio
async def test_control_plane_draft_query_returns_immutable_diff_items(
    async_db_session,
    isolated_control_plane_state,
) -> None:
    async with SessionUnitOfWork(async_db_session) as uow:
        service = TopologyDraftService(uow)
        draft = await service.create_draft(
            DraftCreateCommand(
                name="Immutable diff",
                description="Ensure preview diff returns frozen payloads.",
                access_mode=TopologyAccessMode.CONTROL,
                created_by="ops",
            )
        )
        await service.add_change(
            int(draft.id),
            DraftChangeCommand(
                change_type=TopologyDraftChangeType.ROUTE_CREATED,
                payload={
                    "event_type": "signal_created",
                    "consumer_key": "hypothesis_workers",
                    "status": EventRouteStatus.SHADOW.value,
                    "scope_type": EventRouteScope.SYMBOL.value,
                    "scope_value": "IMMU",
                    "priority": 111,
                },
                created_by="ops",
            ),
        )
        diff = await TopologyDraftQueryService(uow.session).preview_diff(int(draft.id))

    assert len(diff) == 1
    with pytest.raises(FrozenInstanceError):
        diff[0].route_key = "changed"
    with pytest.raises(TypeError):
        diff[0].after["status"] = EventRouteStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_control_plane_persistence_logs_cover_query_and_uow(
    async_db_session,
    isolated_control_plane_state,
    monkeypatch,
) -> None:
    events: list[str] = []

    def _debug(message: str, *args, **kwargs) -> None:
        del args, kwargs
        events.append(message)

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    monkeypatch.setattr(PERSISTENCE_LOGGER, "debug", _debug)
    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)

    async with SessionUnitOfWork(async_db_session) as uow:
        items = await EventRegistryQueryService(uow.session).list_event_definitions()
        route = await RouteManagementService(uow).create_route(
            RouteMutationCommand(
                event_type="signal_created",
                consumer_key="hypothesis_workers",
                status=EventRouteStatus.SHADOW,
                scope_type=EventRouteScope.SYMBOL,
                scope_value="LOGS",
                priority=123,
            ),
            actor=AuditActor(actor="ops"),
        )
        route_key = route.route_key
        await uow.commit()

    assert items
    assert route_key.endswith(":LOGS:*")
    assert "uow.begin" in events
    assert "query.list_event_definitions" in events
    assert "repo.add_route" in events
    assert "uow.commit" in events
