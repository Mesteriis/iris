from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_market_structure_endpoints(api_app_client, seeded_market, monkeypatch) -> None:
    del seeded_market
    _, client = api_app_client

    plugins_response = await client.get("/market-structure/plugins")
    assert plugins_response.status_code == 200
    plugins = {row["name"]: row for row in plugins_response.json()}
    assert {"binance_usdm", "bybit_derivatives", "manual_push"} <= set(plugins)
    assert plugins["manual_push"]["supports_manual_ingest"] is True
    assert plugins["manual_push"]["supports_polling"] is False

    wizard_response = await client.get("/market-structure/onboarding/wizard")
    assert wizard_response.status_code == 200
    wizard = wizard_response.json()
    assert wizard["title"] == "Market Structure Source Wizard"
    assert [preset["id"] for preset in wizard["presets"]] == [
        "binance_usdm",
        "bybit_derivatives",
        "manual_push",
        "liqscope_webhook",
        "liquidation_webhook",
        "derivatives_webhook",
        "coinglass_webhook",
        "hyblock_webhook",
        "coinalyze_webhook",
    ]
    assert any("constructing low-level plugin settings manually" in note for note in wizard["notes"])
    assert any("source-level ingest token" in note for note in wizard["notes"])

    onboarding_binance_response = await client.post(
        "/market-structure/onboarding/sources/binance-usdm",
        json={
            "coin_symbol": "ETHUSD_EVT",
            "timeframe": 15,
        },
    )
    assert onboarding_binance_response.status_code == 201
    onboarding_binance = onboarding_binance_response.json()
    assert onboarding_binance["plugin_name"] == "binance_usdm"
    assert onboarding_binance["display_name"] == "ETHUSD_EVT Binance USD-M"
    assert onboarding_binance["settings"]["market_symbol"] == "ETHUSDT"
    assert onboarding_binance["consecutive_failures"] == 0
    assert onboarding_binance["backoff_until"] is None
    assert onboarding_binance["health"]["status"] == "idle"
    assert onboarding_binance["health"]["backoff_active"] is False
    assert onboarding_binance["health"]["quarantined"] is False

    onboarding_bybit_response = await client.post(
        "/market-structure/onboarding/sources/bybit-derivatives",
        json={
            "coin_symbol": "SOLUSD_EVT",
            "timeframe": 60,
            "category": "linear",
        },
    )
    assert onboarding_bybit_response.status_code == 201
    onboarding_bybit = onboarding_bybit_response.json()
    assert onboarding_bybit["plugin_name"] == "bybit_derivatives"
    assert onboarding_bybit["settings"]["market_symbol"] == "SOLUSDT"
    assert onboarding_bybit["settings"]["category"] == "linear"

    onboarding_manual_response = await client.post(
        "/market-structure/onboarding/sources/manual-push",
        json={
            "coin_symbol": "BTCUSD_EVT",
            "timeframe": 15,
            "venue": "liqscope",
        },
    )
    assert onboarding_manual_response.status_code == 201
    onboarding_manual = onboarding_manual_response.json()
    assert onboarding_manual["plugin_name"] == "manual_push"
    assert onboarding_manual["display_name"] == "BTCUSD_EVT liqscope Feed"
    assert onboarding_manual["settings"]["venue"] == "liqscope"

    liqscope_webhook_response = await client.post(
        "/market-structure/onboarding/sources/liqscope-webhook",
        json={
            "coin_symbol": "ETHUSD_EVT",
            "timeframe": 15,
        },
    )
    assert liqscope_webhook_response.status_code == 201
    liqscope_webhook = liqscope_webhook_response.json()
    assert liqscope_webhook["provider"] == "liqscope"
    assert liqscope_webhook["venue"] == "liqscope"
    assert liqscope_webhook["token"]
    assert liqscope_webhook["token_header"] == "X-IRIS-Ingest-Token"
    assert liqscope_webhook["native_ingest_path"] == f"/market-structure/sources/{liqscope_webhook['source']['id']}/webhook/native"
    assert liqscope_webhook["native_payload_example"]["liquidations"]["long"] == 3300.0
    liqscope_source_id = int(liqscope_webhook["source"]["id"])
    liqscope_token = liqscope_webhook["token"]

    liquidation_webhook_response = await client.post(
        "/market-structure/onboarding/sources/liquidation-webhook",
        json={
            "coin_symbol": "BTCUSD_EVT",
            "timeframe": 15,
        },
    )
    assert liquidation_webhook_response.status_code == 201
    liquidation_webhook = liquidation_webhook_response.json()
    assert liquidation_webhook["provider"] == "liquidation_webhook"
    assert liquidation_webhook["venue"] == "liquidations_api"

    derivatives_webhook_response = await client.post(
        "/market-structure/onboarding/sources/derivatives-webhook",
        json={
            "coin_symbol": "SOLUSD_EVT",
            "timeframe": 15,
        },
    )
    assert derivatives_webhook_response.status_code == 201
    derivatives_webhook = derivatives_webhook_response.json()
    assert derivatives_webhook["provider"] == "derivatives_webhook"
    assert derivatives_webhook["venue"] == "derivatives_webhook"

    coinglass_webhook_response = await client.post(
        "/market-structure/onboarding/sources/coinglass-webhook",
        json={
            "coin_symbol": "ETHUSD_EVT",
            "timeframe": 15,
        },
    )
    assert coinglass_webhook_response.status_code == 201
    coinglass_webhook = coinglass_webhook_response.json()
    assert coinglass_webhook["provider"] == "coinglass"
    assert coinglass_webhook["venue"] == "coinglass"
    assert coinglass_webhook["native_payload_example"]["data"][0]["longLiquidationUsd"] == 5100.0

    hyblock_webhook_response = await client.post(
        "/market-structure/onboarding/sources/hyblock-webhook",
        json={
            "coin_symbol": "BTCUSD_EVT",
            "timeframe": 15,
        },
    )
    assert hyblock_webhook_response.status_code == 201
    hyblock_webhook = hyblock_webhook_response.json()
    assert hyblock_webhook["provider"] == "hyblock"
    assert hyblock_webhook["venue"] == "hyblock"

    coinalyze_webhook_response = await client.post(
        "/market-structure/onboarding/sources/coinalyze-webhook",
        json={
            "coin_symbol": "SOLUSD_EVT",
            "timeframe": 15,
        },
    )
    assert coinalyze_webhook_response.status_code == 201
    coinalyze_webhook = coinalyze_webhook_response.json()
    assert coinalyze_webhook["provider"] == "coinalyze"
    assert coinalyze_webhook["venue"] == "coinalyze"

    create_response = await client.post(
        "/market-structure/sources",
        json={
            "plugin_name": "binance_usdm",
            "display_name": "Binance ETH",
            "settings": {"coin_symbol": "ETHUSD_EVT", "market_symbol": "ETHUSDT", "timeframe": 15},
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["plugin_name"] == "binance_usdm"
    assert created["settings"]["market_symbol"] == "ETHUSDT"

    duplicate = await client.post(
        "/market-structure/sources",
        json={
            "plugin_name": "binance_usdm",
            "display_name": "Binance ETH",
            "settings": {"coin_symbol": "ETHUSD_EVT", "market_symbol": "ETHUSDT", "timeframe": 15},
        },
    )
    assert duplicate.status_code == 400

    sources_response = await client.get("/market-structure/sources")
    assert sources_response.status_code == 200
    assert sorted(row["display_name"] for row in sources_response.json()) == sorted([
        "Binance ETH",
        "ETHUSD_EVT Binance USD-M",
        "ETHUSD_EVT Coinglass Webhook",
        "ETHUSD_EVT Liqscope Webhook",
        "SOLUSD_EVT Bybit Derivatives",
        "SOLUSD_EVT Coinalyze Webhook",
        "BTCUSD_EVT liqscope Feed",
        "BTCUSD_EVT Hyblock Webhook",
        "BTCUSD_EVT Liquidation Webhook",
        "SOLUSD_EVT Derivatives Webhook",
    ])

    webhook_info_response = await client.get(f"/market-structure/sources/{liqscope_source_id}/webhook")
    assert webhook_info_response.status_code == 200
    webhook_info = webhook_info_response.json()
    assert webhook_info["source"]["id"] == liqscope_source_id
    assert webhook_info["token"] is None
    assert webhook_info["token_required"] is True
    assert webhook_info["native_ingest_path"] == f"/market-structure/sources/{liqscope_source_id}/webhook/native"

    health_response = await client.get(f"/market-structure/sources/{liqscope_source_id}/health")
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "idle"
    assert health_response.json()["consecutive_failures"] == 0
    assert health_response.json()["backoff_active"] is False

    unauthorized_ingest_response = await client.post(
        f"/market-structure/sources/{liqscope_source_id}/snapshots",
        json={
            "snapshots": [
                {
                    "timestamp": datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc).isoformat(),
                    "last_price": 3150.0,
                    "liquidations_long": 4000.0,
                }
            ]
        },
    )
    assert unauthorized_ingest_response.status_code == 401

    rotated_webhook_response = await client.post(
        f"/market-structure/sources/{liqscope_source_id}/webhook/rotate-token"
    )
    assert rotated_webhook_response.status_code == 200
    rotated_webhook = rotated_webhook_response.json()
    assert rotated_webhook["token"]
    assert rotated_webhook["token"] != liqscope_token

    old_token_ingest_response = await client.post(
        f"/market-structure/sources/{liqscope_source_id}/snapshots",
        headers={"X-IRIS-Ingest-Token": liqscope_token},
        json={
            "snapshots": [
                {
                    "timestamp": datetime(2026, 3, 12, 12, 1, tzinfo=timezone.utc).isoformat(),
                    "last_price": 3151.0,
                    "liquidations_long": 4100.0,
                }
            ]
        },
    )
    assert old_token_ingest_response.status_code == 401

    authorized_ingest_response = await client.post(
        f"/market-structure/sources/{liqscope_source_id}/snapshots",
        headers={"X-IRIS-Ingest-Token": rotated_webhook["token"]},
        json={
            "snapshots": [
                {
                    "timestamp": datetime(2026, 3, 12, 12, 2, tzinfo=timezone.utc).isoformat(),
                    "last_price": 3152.0,
                    "open_interest": 20800.0,
                    "liquidations_long": 4200.0,
                }
            ]
        },
    )
    assert authorized_ingest_response.status_code == 202
    assert authorized_ingest_response.json()["created"] == 1

    native_ingest_response = await client.post(
        f"/market-structure/sources/{liqscope_source_id}/webhook/native",
        headers={"X-IRIS-Ingest-Token": rotated_webhook["token"]},
        json={
            "timestamp": datetime(2026, 3, 12, 12, 3, tzinfo=timezone.utc).isoformat(),
            "price": 3153.0,
            "open_interest": 20750.0,
            "liquidations": {"long": 4300.0, "short": 150.0},
        },
    )
    assert native_ingest_response.status_code == 202
    assert native_ingest_response.json()["created"] == 1

    refreshed_health_response = await client.get(f"/market-structure/sources/{liqscope_source_id}/health")
    assert refreshed_health_response.status_code == 200
    refreshed_health = refreshed_health_response.json()
    assert refreshed_health["status"] == "healthy"
    assert refreshed_health["last_snapshot_at"] is not None

    coinglass_native_ingest_response = await client.post(
        f"/market-structure/sources/{coinglass_webhook['source']['id']}/webhook/native",
        headers={"X-IRIS-Ingest-Token": coinglass_webhook["token"]},
        json={
            "data": [
                {
                    "time": datetime(2026, 3, 12, 12, 4, tzinfo=timezone.utc).isoformat(),
                    "price": 3154.0,
                    "oi": 20700.0,
                    "funding": 0.0007,
                    "volume24h": 1100000.0,
                    "longLiquidationUsd": 5100.0,
                    "shortLiquidationUsd": 180.0,
                }
            ]
        },
    )
    assert coinglass_native_ingest_response.status_code == 202
    assert coinglass_native_ingest_response.json()["created"] == 1

    source_id = int(created["id"])
    patch_response = await client.patch(
        f"/market-structure/sources/{source_id}",
        json={
            "display_name": "Binance ETH Prime",
            "enabled": False,
            "settings": {"venue": "binance_main"},
            "reset_cursor": True,
            "clear_error": True,
            "release_quarantine": True,
        },
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["display_name"] == "Binance ETH Prime"
    assert patch_response.json()["status"] == "disabled"
    assert patch_response.json()["settings"]["venue"] == "binance_main"

    queued: dict[str, object] = {}
    from app.apps.market_structure.tasks import poll_market_structure_source_job

    async def fake_kiq(**kwargs):
        queued.update(kwargs)

    monkeypatch.setattr(poll_market_structure_source_job, "kiq", fake_kiq)

    queued_response = await client.post(f"/market-structure/sources/{source_id}/jobs/run?limit=2")
    assert queued_response.status_code == 202
    assert queued_response.json() == {"status": "queued", "source_id": source_id, "limit": 2}
    assert queued == {"source_id": source_id, "limit": 2}

    queued_health: dict[str, object] = {}
    from app.apps.market_structure.tasks import refresh_market_structure_source_health_job

    async def fake_health_kiq(**kwargs):
        queued_health.update(kwargs)

    monkeypatch.setattr(refresh_market_structure_source_health_job, "kiq", fake_health_kiq)

    health_job_response = await client.post("/market-structure/health/jobs/run")
    assert health_job_response.status_code == 202
    assert health_job_response.json() == {"status": "queued"}
    assert queued_health == {}

    manual_response = await client.post(
        "/market-structure/sources",
        json={
            "plugin_name": "manual_push",
            "display_name": "Liquidations",
            "settings": {"coin_symbol": "ETHUSD_EVT", "timeframe": 15, "venue": "liqscope"},
        },
    )
    assert manual_response.status_code == 201
    manual_id = int(manual_response.json()["id"])

    ingest_response = await client.post(
        f"/market-structure/sources/{manual_id}/snapshots",
        json={
            "snapshots": [
                {
                    "timestamp": datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc).isoformat(),
                    "last_price": 3150.0,
                    "funding_rate": 0.0009,
                    "open_interest": 21000.0,
                    "liquidations_long": 3300.0,
                    "liquidations_short": 120.0,
                }
            ]
        },
    )
    assert ingest_response.status_code == 202
    assert ingest_response.json()["created"] == 1

    snapshots_response = await client.get("/market-structure/snapshots?coin_symbol=ETHUSD_EVT&venue=liqscope&limit=5")
    assert snapshots_response.status_code == 200
    snapshots = snapshots_response.json()
    assert len(snapshots) == 3
    assert {snapshot["venue"] for snapshot in snapshots} == {"liqscope"}
    assert {snapshot["open_interest"] for snapshot in snapshots} == {20750.0, 20800.0, 21000.0}

    assert (await client.patch("/market-structure/sources/999999", json={"enabled": True})).status_code == 404
    assert (await client.get("/market-structure/sources/999999/health")).status_code == 404
    assert (await client.delete(f"/market-structure/sources/{source_id}")).status_code == 204
    assert (await client.delete(f"/market-structure/sources/{source_id}")).status_code == 404
