from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.apps.anomalies.models import MarketStructureSnapshot
from app.apps.market_structure.models import MarketStructureSource
from app.apps.market_structure.schemas import (
    ManualMarketStructureIngestRequest,
    MarketStructureSnapshotCreate,
    MarketStructureSourceCreate,
    MarketStructureSourceUpdate,
)
from app.apps.market_structure.services import MarketStructureService, MarketStructureSourceProvisioningService
from app.apps.market_structure.exceptions import UnauthorizedMarketStructureIngestError


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, params: dict[str, object] | None = None):
        if "premiumIndex" in url:
            return _FakeResponse(
                {
                    "symbol": params["symbol"],
                    "markPrice": "3150.0",
                    "indexPrice": "3144.4",
                    "lastFundingRate": "0.00102",
                    "time": 1760000010000,
                }
            )
        if "openInterest" in url:
            return _FakeResponse({"openInterest": "19200.0", "symbol": params["symbol"], "time": 1760000010000})
        raise AssertionError(f"Unexpected URL {url}")


class _BrokenAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, params: dict[str, object] | None = None):
        del url, params
        raise RuntimeError("upstream derivatives API unavailable")


@pytest.mark.asyncio
async def test_market_structure_service_polls_persists_and_publishes(async_db_session, seeded_market, monkeypatch) -> None:
    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr("app.apps.market_structure.services.publish_event", lambda name, payload: published.append((name, payload)))
    monkeypatch.setattr("app.apps.market_structure.plugins.httpx.AsyncClient", _FakeAsyncClient)

    service = MarketStructureService(async_db_session)
    source = await service.create_source(
        MarketStructureSourceCreate(
            plugin_name="binance_usdm",
            display_name="Binance ETH",
            credentials={},
            settings={"coin_symbol": "ETHUSD_EVT", "market_symbol": "ETHUSDT", "timeframe": 15},
        )
    )

    result = await service.poll_source(source_id=source.id, limit=1)

    assert result["status"] == "ok"
    assert result["created"] == 1

    stored_source = await async_db_session.get(MarketStructureSource, source.id)
    assert stored_source is not None
    assert stored_source.last_polled_at is not None
    assert stored_source.last_error is None

    snapshot = (
        await async_db_session.execute(
            select(MarketStructureSnapshot)
            .where(MarketStructureSnapshot.symbol == "ETHUSD_EVT", MarketStructureSnapshot.venue == "binance_usdm")
            .limit(1)
        )
    ).scalar_one_or_none()
    assert snapshot is not None
    assert snapshot.funding_rate == pytest.approx(0.00102)
    assert snapshot.open_interest == pytest.approx(19200.0)
    assert snapshot.payload_json["source_id"] == source.id

    event_types = [event_type for event_type, _ in published]
    assert event_types.count("market_structure_source_health_updated") == 2
    assert "market_structure_snapshot_ingested" in event_types
    assert any(
        event_type == "market_structure_source_health_updated"
        and payload["source_id"] == source.id
        and payload["health_status"] == "healthy"
        and payload["symbol"] == "ETHUSD_EVT"
        for event_type, payload in published
    )
    assert any(
        event_type == "market_structure_snapshot_ingested"
        and payload == {
            "coin_id": int(seeded_market["ETHUSD_EVT"]["coin_id"]),
            "timeframe": 15,
            "timestamp": snapshot.timestamp,
            "source_id": source.id,
            "plugin_name": "binance_usdm",
            "symbol": "ETHUSD_EVT",
            "venue": "binance_usdm",
        }
        for event_type, payload in published
    )


@pytest.mark.asyncio
async def test_market_structure_service_manual_ingest_update_and_delete(async_db_session, seeded_market) -> None:
    del seeded_market
    service = MarketStructureService(async_db_session)
    created = await service.create_source(
        MarketStructureSourceCreate(
            plugin_name="manual_push",
            display_name="Liquidation Feed",
            settings={"coin_symbol": "ETHUSD_EVT", "timeframe": 15, "venue": "liqscope"},
        )
    )

    result = await service.ingest_manual_snapshots(
        source_id=created.id,
        payload=ManualMarketStructureIngestRequest(
            snapshots=[
                MarketStructureSnapshotCreate(
                    timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
                    funding_rate=0.0009,
                    open_interest=21000.0,
                    liquidations_long=3300.0,
                    liquidations_short=120.0,
                    last_price=3150.0,
                )
            ]
        ),
    )
    assert result == {
        "status": "ok",
        "source_id": created.id,
        "plugin_name": "manual_push",
        "created": 1,
    }

    snapshots = await service.list_snapshots(coin_symbol="ETHUSD_EVT", venue="liqscope", limit=10)
    assert len(snapshots) == 1
    assert snapshots[0].liquidations_long == pytest.approx(3300.0)

    updated = await service.update_source(
        created.id,
        MarketStructureSourceUpdate(
            display_name="Liquidation Feed Prime",
            enabled=False,
            settings={"venue": "liquidations_api"},
        ),
    )
    assert updated is not None
    assert updated.display_name == "Liquidation Feed Prime"
    assert updated.enabled is False
    assert updated.settings["venue"] == "liquidations_api"

    assert await service.delete_source(created.id) is True
    assert await service.delete_source(created.id) is False


@pytest.mark.asyncio
async def test_market_structure_service_refreshes_stale_health(async_db_session, seeded_market, monkeypatch) -> None:
    del seeded_market
    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr("app.apps.market_structure.services.publish_event", lambda name, payload: published.append((name, payload)))

    service = MarketStructureService(async_db_session)
    created = await service.create_source(
        MarketStructureSourceCreate(
            plugin_name="manual_push",
            display_name="Stale Webhook",
            credentials={"ingest_token": "secret"},
            settings={"coin_symbol": "ETHUSD_EVT", "timeframe": 15, "venue": "liqscope", "provider": "liqscope", "ingest_mode": "webhook"},
        )
    )
    source = await async_db_session.get(MarketStructureSource, created.id)
    assert source is not None
    source.last_polled_at = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    source.last_success_at = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    source.last_snapshot_at = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    source.last_error = None
    source.health_status = "healthy"
    await async_db_session.commit()

    monkeypatch.setattr("app.apps.market_structure.services.utc_now", lambda: datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc))
    result = await service.refresh_source_health()

    assert result == {"status": "ok", "sources": 1, "changed": 1}
    refreshed = await async_db_session.get(MarketStructureSource, created.id)
    assert refreshed is not None
    assert refreshed.health_status == "stale"
    assert any(
        event_type == "market_structure_source_health_updated"
        and payload["source_id"] == created.id
        and payload["health_status"] == "stale"
        and payload["stale"] is True
        for event_type, payload in published
    )
    assert any(
        event_type == "market_structure_source_alerted"
        and payload["source_id"] == created.id
        and payload["alert_kind"] == "stale"
        and payload["rule"] == "source_stale_detected"
        for event_type, payload in published
    )


@pytest.mark.asyncio
async def test_market_structure_service_applies_backoff_quarantine_and_release(async_db_session, seeded_market, monkeypatch) -> None:
    del seeded_market
    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr("app.apps.market_structure.services.publish_event", lambda name, payload: published.append((name, payload)))
    monkeypatch.setattr("app.apps.market_structure.plugins.httpx.AsyncClient", _BrokenAsyncClient)
    monkeypatch.setattr(
        "app.apps.market_structure.services.get_settings",
        lambda: SimpleNamespace(
            taskiq_market_structure_snapshot_poll_interval_seconds=180,
            taskiq_market_structure_failure_backoff_base_seconds=30,
            taskiq_market_structure_failure_backoff_max_seconds=120,
            taskiq_market_structure_quarantine_after_failures=3,
        ),
    )

    service = MarketStructureService(async_db_session)
    created = await service.create_source(
        MarketStructureSourceCreate(
            plugin_name="binance_usdm",
            display_name="Binance ETH Failing",
            settings={"coin_symbol": "ETHUSD_EVT", "market_symbol": "ETHUSDT", "timeframe": 15},
        )
    )

    first_failure = await service.poll_source(source_id=created.id, limit=1)
    assert first_failure["status"] == "error"
    assert first_failure["consecutive_failures"] == 1
    assert first_failure["quarantined"] is False
    assert first_failure["backoff_until"] is not None

    backoff_skip = await service.poll_source(source_id=created.id, limit=1)
    assert backoff_skip["status"] == "skipped"
    assert backoff_skip["reason"] == "source_backoff"

    source = await async_db_session.get(MarketStructureSource, created.id)
    assert source is not None
    source.backoff_until = datetime(2000, 1, 1, tzinfo=timezone.utc)
    await async_db_session.commit()

    second_failure = await service.poll_source(source_id=created.id, limit=1)
    assert second_failure["status"] == "error"
    assert second_failure["consecutive_failures"] == 2
    assert second_failure["quarantined"] is False

    source = await async_db_session.get(MarketStructureSource, created.id)
    assert source is not None
    source.backoff_until = datetime(2000, 1, 1, tzinfo=timezone.utc)
    await async_db_session.commit()

    third_failure = await service.poll_source(source_id=created.id, limit=1)
    assert third_failure["status"] == "error"
    assert third_failure["consecutive_failures"] == 3
    assert third_failure["quarantined"] is True
    assert third_failure["quarantine_reason"]

    quarantined = await async_db_session.get(MarketStructureSource, created.id)
    assert quarantined is not None
    assert quarantined.enabled is False
    assert quarantined.health_status == "quarantined"
    assert quarantined.last_alert_kind == "quarantined"

    quarantined_skip = await service.poll_source(source_id=created.id, limit=1)
    assert quarantined_skip["status"] == "skipped"
    assert quarantined_skip["reason"] == "source_quarantined"

    released = await service.update_source(
        created.id,
        MarketStructureSourceUpdate(
            enabled=True,
            clear_error=True,
            release_quarantine=True,
        ),
    )
    assert released is not None
    assert released.enabled is True
    assert released.status == "active"
    assert released.health.status == "idle"
    assert released.consecutive_failures == 0
    assert released.backoff_until is None
    assert released.quarantined_at is None
    assert released.quarantine_reason is None

    alerted_events = [payload for event_type, payload in published if event_type == "market_structure_source_alerted"]
    assert [payload["alert_kind"] for payload in alerted_events] == ["error", "quarantined"]
    assert any(
        event_type == "market_structure_source_quarantined"
        and payload["source_id"] == created.id
        and payload["alert_kind"] == "quarantined"
        for event_type, payload in published
    )


@pytest.mark.asyncio
async def test_market_structure_service_poll_enabled_sources_skips_manual(async_db_session, seeded_market, monkeypatch) -> None:
    del seeded_market
    monkeypatch.setattr("app.apps.market_structure.plugins.httpx.AsyncClient", _FakeAsyncClient)
    service = MarketStructureService(async_db_session)

    await service.create_source(
        MarketStructureSourceCreate(
            plugin_name="binance_usdm",
            display_name="Binance ETH",
            settings={"coin_symbol": "ETHUSD_EVT", "market_symbol": "ETHUSDT", "timeframe": 15},
        )
    )
    await service.create_source(
        MarketStructureSourceCreate(
            plugin_name="manual_push",
            display_name="Manual ETH",
            settings={"coin_symbol": "ETHUSD_EVT", "timeframe": 15, "venue": "liqscope"},
        )
    )

    result = await service.poll_enabled_sources(limit_per_source=1)

    assert result["status"] == "ok"
    assert result["sources"] == 2
    assert any(item["status"] == "ok" for item in result["items"])
    assert any(item["reason"] == "plugin_requires_manual_ingest" for item in result["items"] if item["status"] == "skipped")


@pytest.mark.asyncio
async def test_market_structure_provisioning_service_builds_frontend_friendly_sources(async_db_session, seeded_market) -> None:
    del seeded_market
    provisioning = MarketStructureSourceProvisioningService(async_db_session)

    binance = await provisioning.create_binance_source(
        payload={
            "coin_symbol": "ETHUSD_EVT",
            "timeframe": 15,
        }
    )
    bybit = await provisioning.create_bybit_source(
        payload={
            "coin_symbol": "SOLUSD_EVT",
            "timeframe": 60,
            "category": "linear",
        }
    )
    manual = await provisioning.create_manual_source(
        payload={
            "coin_symbol": "BTCUSD_EVT",
            "timeframe": 15,
            "venue": "liqscope",
        }
    )
    webhook = await provisioning.create_liqscope_webhook_source(
        payload={
            "coin_symbol": "ETHUSD_EVT",
            "timeframe": 15,
        }
    )
    coinglass = await provisioning.create_coinglass_webhook_source(
        payload={
            "coin_symbol": "BTCUSD_EVT",
            "timeframe": 15,
        }
    )

    assert binance.plugin_name == "binance_usdm"
    assert binance.settings["market_symbol"] == "ETHUSDT"
    assert binance.display_name == "ETHUSD_EVT Binance USD-M"

    assert bybit.plugin_name == "bybit_derivatives"
    assert bybit.settings["market_symbol"] == "SOLUSDT"
    assert bybit.settings["category"] == "linear"

    assert manual.plugin_name == "manual_push"
    assert manual.settings["venue"] == "liqscope"
    assert manual.display_name == "BTCUSD_EVT liqscope Feed"
    assert webhook.source.plugin_name == "manual_push"
    assert webhook.provider == "liqscope"
    assert webhook.venue == "liqscope"
    assert webhook.ingest_path == f"/market-structure/sources/{webhook.source.id}/snapshots"
    assert webhook.native_ingest_path == f"/market-structure/sources/{webhook.source.id}/webhook/native"
    assert webhook.token
    assert webhook.native_payload_example["liquidations"]["long"] == 3300.0
    assert webhook.source.credential_fields_present == ["ingest_token"]
    assert coinglass.provider == "coinglass"
    assert coinglass.venue == "coinglass"
    assert coinglass.native_payload_example["data"][0]["longLiquidationUsd"] == 5100.0

    wizard = provisioning.wizard_spec()
    assert wizard.presets[0].endpoint == "/market-structure/onboarding/sources/binance-usdm"
    assert any("low-level plugin settings" in note for note in wizard.notes)
    assert any("rotated from the frontend" in note for note in wizard.notes)
    assert any(preset.id == "coinglass_webhook" for preset in wizard.presets)
    assert any(preset.id == "hyblock_webhook" for preset in wizard.presets)
    assert any(preset.id == "coinalyze_webhook" for preset in wizard.presets)

    registration = await provisioning.read_webhook_registration(webhook.source.id, include_token=False)
    assert registration is not None
    assert registration.token is None
    assert registration.token_required is True
    assert registration.native_ingest_path == webhook.native_ingest_path

    rotated = await provisioning.rotate_webhook_token(webhook.source.id)
    assert rotated is not None
    assert rotated.token
    assert rotated.token != webhook.token

    service = MarketStructureService(async_db_session)
    with pytest.raises(UnauthorizedMarketStructureIngestError):
        await service.ingest_manual_snapshots(
            source_id=webhook.source.id,
            payload=ManualMarketStructureIngestRequest(
                snapshots=[
                    MarketStructureSnapshotCreate(
                        timestamp=datetime(2026, 3, 12, 12, 5, tzinfo=timezone.utc),
                        funding_rate=0.0007,
                        open_interest=20500.0,
                    )
                ]
            ),
        )

    result = await service.ingest_manual_snapshots(
        source_id=webhook.source.id,
        ingest_token=rotated.token,
        payload=ManualMarketStructureIngestRequest(
            snapshots=[
                MarketStructureSnapshotCreate(
                    timestamp=datetime(2026, 3, 12, 12, 5, tzinfo=timezone.utc),
                    funding_rate=0.0007,
                    open_interest=20500.0,
                    liquidations_long=900.0,
                )
            ]
        ),
    )
    assert result["status"] == "ok"
    assert result["created"] == 1

    native_result = await service.ingest_native_webhook_payload(
        source_id=webhook.source.id,
        ingest_token=rotated.token,
        payload={
            "timestamp": datetime(2026, 3, 12, 12, 10, tzinfo=timezone.utc).isoformat(),
            "price": 3160.0,
            "open_interest": 20600.0,
            "liquidations": {"long": 1200.0, "short": 90.0},
        },
    )
    assert native_result["status"] == "ok"
    assert native_result["created"] == 1
