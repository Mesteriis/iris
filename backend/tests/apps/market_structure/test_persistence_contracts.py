from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timezone

import pytest
from src.apps.market_structure.query_services import MarketStructureQueryService
from src.apps.market_structure.schemas import (
    ManualMarketStructureIngestRequest,
    MarketStructureSnapshotCreate,
    MarketStructureSourceCreate,
)
from src.apps.market_structure.services import MarketStructureService, MarketStructureSourceProvisioningService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_market_structure_query_returns_immutable_read_models(async_db_session, seeded_market) -> None:
    del seeded_market
    async with SessionUnitOfWork(async_db_session) as uow:
        service = MarketStructureService(uow)
        query_service = MarketStructureQueryService(uow.session)
        created = await service.create_source(
            MarketStructureSourceCreate(
                plugin_name="manual_push",
                display_name="Immutable Feed",
                credentials={"ingest_token": "secret-token"},
                settings={"coin_symbol": "ETHUSD_EVT", "timeframe": 15, "venue": "liqscope"},
            )
        )
        await service.ingest_manual_snapshots(
            source_id=created.id,
            ingest_token="secret-token",
            payload=ManualMarketStructureIngestRequest(
                snapshots=[
                    MarketStructureSnapshotCreate(
                        timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=UTC),
                        open_interest=21000.0,
                        liquidations_long=3300.0,
                    )
                ]
            ),
        )
        sources = await query_service.list_sources()
        snapshots = await query_service.list_snapshots(coin_symbol="ETHUSD_EVT", venue="liqscope", limit=10)
        await uow.commit()

    source = next(item for item in sources if item.id == created.id)
    assert len(snapshots) == 1
    with pytest.raises(FrozenInstanceError):
        source.display_name = "changed"
    with pytest.raises(TypeError):
        source.settings["venue"] = "other"
    with pytest.raises(FrozenInstanceError):
        source.health.status = "error"
    with pytest.raises(FrozenInstanceError):
        snapshots[0].venue = "other"
    with pytest.raises(TypeError):
        snapshots[0].payload_json["source_id"] = 999


@pytest.mark.asyncio
async def test_market_structure_query_returns_immutable_webhook_registration(async_db_session, seeded_market) -> None:
    del seeded_market
    async with SessionUnitOfWork(async_db_session) as uow:
        provisioning = MarketStructureSourceProvisioningService(uow)
        registration = await provisioning.create_liqscope_webhook_source(
            payload={
                "coin_symbol": "ETHUSD_EVT",
                "timeframe": 15,
            }
        )
        item = await MarketStructureQueryService(uow.session).get_webhook_registration_read_by_id(
            int(registration.source.id),
            include_token=False,
        )
        await uow.commit()

    assert item is not None
    assert item.token is None
    with pytest.raises(FrozenInstanceError):
        item.provider = "other"
    with pytest.raises(TypeError):
        item.native_payload_example["liquidations"] = {}


@pytest.mark.asyncio
async def test_market_structure_persistence_logs_cover_query_repo_and_uow(
    async_db_session, seeded_market, monkeypatch
) -> None:
    del seeded_market
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
        await MarketStructureService(uow).create_source(
            MarketStructureSourceCreate(
                plugin_name="manual_push",
                display_name="Log Feed",
                settings={"coin_symbol": "ETHUSD_EVT", "timeframe": 15, "venue": "liqscope"},
            )
        )
        items = await MarketStructureQueryService(uow.session).list_sources()
        await uow.commit()

    assert items
    assert "uow.begin" in events
    assert "repo.add_market_structure_source" in events
    assert "query.list_market_structure_sources" in events
    assert "uow.commit" in events


@pytest.mark.asyncio
async def test_market_structure_side_effects_run_only_after_uow_commit(
    async_db_session, seeded_market, monkeypatch
) -> None:
    del seeded_market
    published: list[str] = []
    monkeypatch.setattr(
        "src.apps.market_structure.services.side_effects.publish_event",
        lambda event_name, payload: published.append(event_name),
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        await MarketStructureService(uow).create_source(
            MarketStructureSourceCreate(
                plugin_name="manual_push",
                display_name="Deferred Event Feed",
                settings={"coin_symbol": "ETHUSD_EVT", "timeframe": 15, "venue": "liqscope"},
            )
        )
        assert published == []
        await uow.commit()

    assert published == ["market_structure_source_health_updated"]
