from __future__ import annotations

import pytest

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
