from __future__ import annotations

import importlib.util

import pytest
from src.apps.indicators.api.router import build_router as build_indicators_router
from src.core.http.launch_modes import DeploymentProfile, LaunchMode

from tests.factories.base import json_utc


@pytest.mark.asyncio
async def test_indicator_endpoints(api_app_client, seeded_api_state) -> None:
    _, client = api_app_client

    metrics_response = await client.get("/coins/metrics")
    assert metrics_response.status_code == 200
    metrics_payload = metrics_response.json()
    evt_metrics = {row["symbol"]: row for row in metrics_payload if row["symbol"].endswith("_EVT")}
    assert {"BTCUSD_EVT", "ETHUSD_EVT", "SOLUSD_EVT"} <= evt_metrics.keys()
    assert evt_metrics["BTCUSD_EVT"]["market_regime"] == "bull_trend"

    cycles_response = await client.get("/market/cycle?symbol=BTCUSD_EVT&timeframe=15")
    assert cycles_response.status_code == 200
    cycle_payload = cycles_response.json()
    assert cycle_payload == [
        {
            "coin_id": seeded_api_state["btc"].id,
            "symbol": "BTCUSD_EVT",
            "name": "Bitcoin Event Test",
            "timeframe": 15,
            "cycle_phase": "markup",
            "confidence": 0.84,
            "detected_at": cycle_payload[0]["detected_at"],
        }
    ]
    assert cycle_payload[0]["detected_at"].startswith("2026-03-03T04:00:00")

    radar_response = await client.get("/market/radar?limit=24")
    assert radar_response.status_code == 200
    radar_payload = radar_response.json()
    assert any(row["symbol"] == "BTCUSD_EVT" for row in radar_payload["hot_coins"])
    assert any(row["symbol"] == "BTCUSD_EVT" and row["regime"] == "bull_trend" for row in radar_payload["regime_changes"])
    assert radar_payload["consistency"] == "derived"
    assert radar_payload["freshness_class"] == "near_real_time"
    assert isinstance(radar_payload["generated_at"], str) and radar_payload["generated_at"]
    assert isinstance(radar_payload["staleness_ms"], int)
    assert radar_response.headers["cache-control"] == "public, max-age=15, stale-while-revalidate=30"
    assert radar_response.headers["etag"].startswith('W/"')

    radar_not_modified_response = await client.get(
        "/market/radar?limit=24",
        headers={"If-None-Match": radar_response.headers["etag"]},
    )
    assert radar_not_modified_response.status_code == 304

    flow_response = await client.get("/market/flow?limit=24&timeframe=60")
    assert flow_response.status_code == 200
    flow_payload = flow_response.json()
    assert any(row["symbol"] == "BTCUSD_EVT" for row in flow_payload["leaders"])
    assert any(
        row["leader_symbol"] == "BTCUSD_EVT" and row["follower_symbol"] == "ETHUSD_EVT"
        for row in flow_payload["relations"]
    )
    assert any(row["sector"] == "store_of_value" for row in flow_payload["sectors"])
    assert flow_payload["rotations"][0] == {
        "source_sector": "store_of_value",
        "target_sector": "smart_contract",
        "timeframe": 60,
        "timestamp": json_utc(seeded_api_state["signal_timestamp"]),
    }
    assert flow_payload["consistency"] == "derived"
    assert flow_payload["freshness_class"] == "near_real_time"
    assert isinstance(flow_payload["generated_at"], str) and flow_payload["generated_at"]
    assert isinstance(flow_payload["staleness_ms"], int)
    assert flow_response.headers["cache-control"] == "public, max-age=15, stale-while-revalidate=30"
    assert flow_response.headers["etag"].startswith('W/"')

    flow_not_modified_response = await client.get(
        "/market/flow?limit=24&timeframe=60",
        headers={"If-None-Match": flow_response.headers["etag"]},
    )
    assert flow_not_modified_response.status_code == 304


def test_indicators_api_router_is_mode_agnostic_and_legacy_views_removed() -> None:
    full_router = build_indicators_router(mode=LaunchMode.FULL, profile=DeploymentProfile.PLATFORM_FULL)
    ha_router = build_indicators_router(mode=LaunchMode.HA_ADDON, profile=DeploymentProfile.HA_EMBEDDED)

    full_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in full_router.routes}
    ha_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in ha_router.routes}

    assert full_paths == ha_paths
    assert any(path == "/coins/metrics" and "GET" in methods for path, methods in full_paths)
    assert any(path == "/market/cycle" and "GET" in methods for path, methods in full_paths)
    assert any(path == "/market/flow" and "GET" in methods for path, methods in full_paths)
    assert importlib.util.find_spec("src.apps.indicators.views") is None
