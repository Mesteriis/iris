from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_pattern_endpoints(api_app_client, seeded_api_state) -> None:
    _, client = api_app_client

    patterns_response = await client.get("/patterns")
    assert patterns_response.status_code == 200
    assert {"bull_flag", "breakout_retest"} <= {row["slug"] for row in patterns_response.json()}

    features_response = await client.get("/patterns/features")
    assert features_response.status_code == 200
    assert {"market_regime_engine", "pattern_context_engine"} <= {
        row["feature_slug"] for row in features_response.json()
    }

    patch_feature_response = await client.patch(
        "/patterns/features/pattern_context_engine",
        json={"enabled": False},
    )
    assert patch_feature_response.status_code == 200
    assert patch_feature_response.json()["enabled"] is False

    missing_feature_response = await client.patch(
        "/patterns/features/missing_feature",
        json={"enabled": False},
    )
    assert missing_feature_response.status_code == 404
    assert missing_feature_response.json()["detail"] == "Pattern feature 'missing_feature' was not found."

    patch_pattern_response = await client.patch(
        "/patterns/bull_flag",
        json={"enabled": True, "lifecycle_state": "experimental", "cpu_cost": 0},
    )
    assert patch_pattern_response.status_code == 200
    patched_pattern = patch_pattern_response.json()
    assert patched_pattern["slug"] == "bull_flag"
    assert patched_pattern["lifecycle_state"] == "EXPERIMENTAL"
    assert patched_pattern["cpu_cost"] == 1

    invalid_pattern_response = await client.patch(
        "/patterns/bull_flag",
        json={"lifecycle_state": "not_real"},
    )
    assert invalid_pattern_response.status_code == 400
    assert invalid_pattern_response.json()["detail"] == "Unsupported lifecycle state 'not_real'."

    missing_pattern_response = await client.patch(
        "/patterns/missing_pattern",
        json={"enabled": True},
    )
    assert missing_pattern_response.status_code == 404
    assert missing_pattern_response.json()["detail"] == "Pattern 'missing_pattern' was not found."

    discovered_response = await client.get("/patterns/discovered?timeframe=15&limit=10")
    assert discovered_response.status_code == 200
    assert discovered_response.json()[0]["structure_hash"] == "cluster:bull_flag:15"

    coin_patterns_response = await client.get("/coins/BTCUSD_EVT/patterns?limit=10")
    assert coin_patterns_response.status_code == 200
    coin_patterns = coin_patterns_response.json()
    assert [row["signal_type"] for row in coin_patterns] == [
        "pattern_bull_flag",
        "pattern_cluster_breakout",
    ]
    assert coin_patterns[0]["cluster_membership"] == ["pattern_cluster_breakout"]

    regime_response = await client.get("/coins/BTCUSD_EVT/regime")
    assert regime_response.status_code == 200
    regime_payload = regime_response.json()
    assert regime_payload["canonical_regime"] == "bull_trend"
    assert regime_payload["items"] == [
        {"timeframe": 15, "regime": "bull_trend", "confidence": 0.81},
        {"timeframe": 60, "regime": "bull_trend", "confidence": 0.79},
    ]

    missing_regime_response = await client.get("/coins/MISSING_EVT/regime")
    assert missing_regime_response.status_code == 404
    assert missing_regime_response.json()["detail"] == "Coin 'MISSING_EVT' was not found."

    sectors_response = await client.get("/sectors")
    assert sectors_response.status_code == 200
    sector_payload = sectors_response.json()
    sector_map = {row["name"]: row for row in sector_payload}
    assert {"high_beta", "smart_contract", "store_of_value"} <= sector_map.keys()
    assert sector_map["store_of_value"]["coin_count"] == 1

    sector_metrics_response = await client.get("/sectors/metrics?timeframe=60")
    assert sector_metrics_response.status_code == 200
    sector_metrics_payload = sector_metrics_response.json()
    assert [row["name"] for row in sector_metrics_payload["items"]] == ["store_of_value", "smart_contract"]
    assert sector_metrics_payload["narratives"][0]["timeframe"] == 60
    assert sector_metrics_payload["narratives"][0]["top_sector"] == "store_of_value"


@pytest.mark.asyncio
async def test_pattern_view_branches(monkeypatch) -> None:
    from app.apps.patterns.views import patch_pattern, patch_pattern_feature, read_coin_regime

    async def missing_row(*_args, **_kwargs):
        return None

    async def feature_row(*_args, **_kwargs):
        return {
            "feature_slug": "market_regime_engine",
            "enabled": True,
            "created_at": "2026-03-12T00:00:00Z",
        }

    monkeypatch.setattr("app.apps.patterns.views.update_pattern_feature_async", missing_row)
    with pytest.raises(HTTPException) as missing_feature:
        await patch_pattern_feature("missing", SimpleNamespace(enabled=True), db=object())
    assert missing_feature.value.status_code == 404

    monkeypatch.setattr("app.apps.patterns.views.update_pattern_feature_async", feature_row)
    feature = await patch_pattern_feature("market_regime_engine", SimpleNamespace(enabled=True), db=object())
    assert feature.feature_slug == "market_regime_engine"

    async def invalid_pattern(*_args, **_kwargs):
        raise ValueError("bad pattern")

    monkeypatch.setattr("app.apps.patterns.views.update_pattern_async", invalid_pattern)
    with pytest.raises(HTTPException) as invalid:
        await patch_pattern("bull_flag", SimpleNamespace(enabled=True, lifecycle_state=None, cpu_cost=None), db=object())
    assert invalid.value.status_code == 400

    monkeypatch.setattr("app.apps.patterns.views.update_pattern_async", missing_row)
    with pytest.raises(HTTPException) as missing_pattern:
        await patch_pattern("missing", SimpleNamespace(enabled=True, lifecycle_state=None, cpu_cost=None), db=object())
    assert missing_pattern.value.status_code == 404

    async def pattern_row(*_args, **_kwargs):
        return {
            "slug": "bull_flag",
            "category": "continuation",
            "enabled": True,
            "cpu_cost": 1,
            "lifecycle_state": "ACTIVE",
            "created_at": "2026-03-12T00:00:00Z",
            "statistics": [],
        }

    monkeypatch.setattr("app.apps.patterns.views.update_pattern_async", pattern_row)
    pattern = await patch_pattern("bull_flag", SimpleNamespace(enabled=True, lifecycle_state=None, cpu_cost=1), db=object())
    assert pattern.slug == "bull_flag"

    monkeypatch.setattr("app.apps.patterns.views.get_coin_regimes_async", missing_row)
    with pytest.raises(HTTPException) as missing_regime:
        await read_coin_regime("BTCUSD_EVT", db=object())
    assert missing_regime.value.status_code == 404

    async def regime_payload(*_args, **_kwargs):
        return {"coin_id": 1, "symbol": "BTCUSD_EVT", "canonical_regime": "bull_trend", "items": []}

    monkeypatch.setattr("app.apps.patterns.views.get_coin_regimes_async", regime_payload)
    regime = await read_coin_regime("BTCUSD_EVT", db=object())
    assert regime.symbol == "BTCUSD_EVT"
