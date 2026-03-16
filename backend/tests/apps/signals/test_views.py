import importlib.util
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from src.apps.signals.api.backtest_endpoints import read_coin_backtests
from src.apps.signals.api.decision_endpoints import read_coin_decision
from src.apps.signals.api.final_signal_endpoints import read_coin_final_signal
from src.apps.signals.api.market_decision_endpoints import read_coin_market_decision
from src.apps.signals.api.router import build_router as build_signals_router
from src.apps.signals.query_services import SignalQueryService
from src.core.http.launch_modes import DeploymentProfile, LaunchMode

from tests.factories.base import json_utc


@pytest.mark.asyncio
async def test_signal_and_strategy_endpoints(api_app_client, seeded_api_state) -> None:
    _, client = api_app_client

    signals_response = await client.get("/signals?symbol=BTCUSD_EVT&timeframe=15&limit=10")
    assert signals_response.status_code == 200
    signals_payload = signals_response.json()
    assert [row["signal_type"] for row in signals_payload] == [
        "pattern_bull_flag",
        "pattern_cluster_breakout",
    ]
    assert signals_payload[0]["cycle_phase"] == "markup"

    top_signals_response = await client.get("/signals/top?limit=200")
    assert top_signals_response.status_code == 200
    assert any(
        row["symbol"] == "BTCUSD_EVT" and row["signal_type"] == "pattern_bull_flag"
        for row in top_signals_response.json()
    )

    decisions_response = await client.get("/decisions?symbol=BTCUSD_EVT&timeframe=15")
    assert decisions_response.status_code == 200
    decisions_payload = decisions_response.json()
    assert decisions_payload == [
        {
            "id": decisions_payload[0]["id"],
            "coin_id": seeded_api_state["btc"].id,
            "symbol": "BTCUSD_EVT",
            "name": "Bitcoin Event Test",
            "sector": "store_of_value",
            "timeframe": 15,
            "decision": "BUY",
            "confidence": 0.82,
            "score": 99.1,
            "reason": "Bullish pattern stack",
            "created_at": json_utc(seeded_api_state["signal_timestamp"]),
        }
    ]

    top_decisions_response = await client.get("/decisions/top?limit=200")
    assert top_decisions_response.status_code == 200
    assert any(
        row["symbol"] == "BTCUSD_EVT" and row["decision"] == "BUY"
        for row in top_decisions_response.json()
    )

    coin_decision_response = await client.get("/coins/BTCUSD_EVT/decision")
    assert coin_decision_response.status_code == 200
    assert coin_decision_response.json() == {
        "coin_id": seeded_api_state["btc"].id,
        "symbol": "BTCUSD_EVT",
        "canonical_decision": "BUY",
        "items": [
            {
                "timeframe": 15,
                "decision": "BUY",
                "confidence": 0.82,
                "score": 99.1,
                "reason": "Bullish pattern stack",
                "created_at": json_utc(seeded_api_state["signal_timestamp"]),
            }
        ],
    }

    missing_decision_response = await client.get("/coins/MISSING_EVT/decision")
    assert missing_decision_response.status_code == 404
    assert missing_decision_response.json()["detail"]["message"] == "Coin 'MISSING_EVT' was not found."

    market_decisions_response = await client.get("/market-decisions?symbol=BTCUSD_EVT&limit=10")
    assert market_decisions_response.status_code == 200
    market_decisions_payload = market_decisions_response.json()
    assert market_decisions_payload == [
        {
            "id": market_decisions_payload[0]["id"],
            "coin_id": seeded_api_state["btc"].id,
            "symbol": "BTCUSD_EVT",
            "name": "Bitcoin Event Test",
            "sector": "store_of_value",
            "timeframe": 15,
            "decision": "BUY",
            "confidence": 0.998,
            "signal_count": 3,
            "regime": "bull_trend",
            "created_at": json_utc(seeded_api_state["signal_timestamp"]),
        }
    ]

    top_market_decisions_response = await client.get("/market-decisions/top?limit=200")
    assert top_market_decisions_response.status_code == 200
    assert any(
        row["symbol"] == "BTCUSD_EVT" and row["decision"] == "BUY"
        for row in top_market_decisions_response.json()
    )

    coin_market_decision_response = await client.get("/coins/BTCUSD_EVT/market-decision")
    assert coin_market_decision_response.status_code == 200
    coin_market_decision_payload = coin_market_decision_response.json()
    assert coin_market_decision_payload["coin_id"] == seeded_api_state["btc"].id
    assert coin_market_decision_payload["symbol"] == "BTCUSD_EVT"
    assert coin_market_decision_payload["canonical_decision"] == "BUY"
    assert coin_market_decision_payload["items"] == [
        {
            "timeframe": 15,
            "decision": "BUY",
            "confidence": 0.998,
            "signal_count": 3,
            "regime": "bull_trend",
            "created_at": json_utc(seeded_api_state["signal_timestamp"]),
        }
    ]
    assert coin_market_decision_payload["consistency"] == "snapshot"
    assert coin_market_decision_payload["freshness_class"] == "near_real_time"
    assert isinstance(coin_market_decision_payload["generated_at"], str) and coin_market_decision_payload["generated_at"]
    assert isinstance(coin_market_decision_payload["staleness_ms"], int)
    assert coin_market_decision_response.headers["cache-control"] == "public, max-age=15, stale-while-revalidate=30"
    assert coin_market_decision_response.headers["etag"].startswith('W/"')

    coin_market_decision_not_modified_response = await client.get(
        "/coins/BTCUSD_EVT/market-decision",
        headers={"If-None-Match": coin_market_decision_response.headers["etag"]},
    )
    assert coin_market_decision_not_modified_response.status_code == 304

    missing_market_decision_response = await client.get("/coins/MISSING_EVT/market-decision")
    assert missing_market_decision_response.status_code == 404
    assert missing_market_decision_response.json()["detail"]["message"] == "Coin 'MISSING_EVT' was not found."

    final_signals_response = await client.get("/final-signals?symbol=BTCUSD_EVT&limit=10")
    assert final_signals_response.status_code == 200
    final_signals_payload = final_signals_response.json()
    assert final_signals_payload[0]["decision"] == "BUY"
    assert final_signals_payload[0]["liquidity_score"] == 0.87

    top_final_signals_response = await client.get("/final-signals/top?limit=200")
    assert top_final_signals_response.status_code == 200
    assert any(
        row["symbol"] == "BTCUSD_EVT" and row["risk_adjusted_score"] == 99.69
        for row in top_final_signals_response.json()
    )

    coin_final_signal_response = await client.get("/coins/BTCUSD_EVT/final-signal")
    assert coin_final_signal_response.status_code == 200
    assert coin_final_signal_response.json() == {
        "coin_id": seeded_api_state["btc"].id,
        "symbol": "BTCUSD_EVT",
        "canonical_decision": "BUY",
        "items": [
            {
                "timeframe": 15,
                "decision": "BUY",
                "confidence": 0.77,
                "risk_adjusted_score": 99.69,
                "liquidity_score": 0.87,
                "slippage_risk": 0.09,
                "volatility_risk": 0.18,
                "reason": "Aligned trend and acceptable risk",
                "created_at": json_utc(seeded_api_state["signal_timestamp"]),
            }
        ],
    }

    missing_final_signal_response = await client.get("/coins/MISSING_EVT/final-signal")
    assert missing_final_signal_response.status_code == 404
    assert missing_final_signal_response.json()["detail"]["message"] == "Coin 'MISSING_EVT' was not found."

    backtests_response = await client.get("/backtests?symbol=BTCUSD_EVT&timeframe=15&signal_type=pattern_bull_flag")
    assert backtests_response.status_code == 200
    backtests_payload = backtests_response.json()
    assert backtests_payload[0]["sample_size"] == 2
    assert backtests_payload[0]["coin_count"] == 1

    top_backtests_response = await client.get("/backtests/top?timeframe=15&limit=200")
    assert top_backtests_response.status_code == 200
    assert any(
        row["signal_type"] == "pattern_bull_flag" and row["timeframe"] == 15
        for row in top_backtests_response.json()
    )

    coin_backtests_response = await client.get("/coins/BTCUSD_EVT/backtests?timeframe=15&signal_type=pattern_bull_flag")
    assert coin_backtests_response.status_code == 200
    coin_backtests_payload = coin_backtests_response.json()
    assert coin_backtests_payload["coin_id"] == seeded_api_state["btc"].id
    assert coin_backtests_payload["items"][0]["signal_type"] == "pattern_bull_flag"

    missing_backtests_response = await client.get("/coins/MISSING_EVT/backtests")
    assert missing_backtests_response.status_code == 404
    assert missing_backtests_response.json()["detail"]["message"] == "Coin 'MISSING_EVT' was not found."

    strategies_response = await client.get("/strategies?enabled_only=true")
    assert strategies_response.status_code == 200
    strategies_payload = strategies_response.json()
    assert strategies_payload == [
        {
            "id": 101,
            "name": "Momentum Breakout",
            "description": "Pattern-led continuation entries",
            "enabled": True,
            "created_at": json_utc(seeded_api_state["signal_timestamp"]),
            "rules": [
                {
                    "pattern_slug": "bull_flag",
                    "regime": "bull_trend",
                    "sector": "store_of_value",
                    "cycle": "markup",
                    "min_confidence": 0.7,
                }
            ],
            "performance": {
                "strategy_id": 101,
                "name": "Momentum Breakout",
                "enabled": True,
                "sample_size": 18,
                "win_rate": 0.67,
                "avg_return": 0.031,
                "sharpe_ratio": 1.48,
                "max_drawdown": -0.09,
                "updated_at": json_utc(seeded_api_state["signal_timestamp"]),
            },
        }
    ]

    strategy_performance_response = await client.get("/strategies/performance?limit=5")
    assert strategy_performance_response.status_code == 200
    assert strategy_performance_response.json() == [
        {
            "strategy_id": 101,
            "name": "Momentum Breakout",
            "enabled": True,
            "sample_size": 18,
            "win_rate": 0.67,
            "avg_return": 0.031,
            "sharpe_ratio": 1.48,
            "max_drawdown": -0.09,
            "updated_at": json_utc(seeded_api_state["signal_timestamp"]),
        }
    ]


@pytest.mark.asyncio
async def test_signal_view_branches(monkeypatch) -> None:
    async def missing_payload(self, *_args, **_kwargs):
        del self
        return

    service = SignalQueryService(object())

    monkeypatch.setattr(service, "get_coin_decision", missing_payload.__get__(service, SignalQueryService))
    with pytest.raises(HTTPException) as missing_decision:
        await read_coin_decision("BTCUSD_EVT", service=service)
    assert missing_decision.value.status_code == 404

    monkeypatch.setattr(
        service,
        "get_coin_market_decision",
        missing_payload.__get__(service, SignalQueryService),
    )
    with pytest.raises(HTTPException) as missing_market_decision:
        await read_coin_market_decision(
            "BTCUSD_EVT",
            request=SimpleNamespace(headers={}),
            response=Response(),
            service=service,
        )
    assert missing_market_decision.value.status_code == 404

    monkeypatch.setattr(
        service,
        "get_coin_final_signal",
        missing_payload.__get__(service, SignalQueryService),
    )
    with pytest.raises(HTTPException) as missing_final_signal:
        await read_coin_final_signal("BTCUSD_EVT", service=service)
    assert missing_final_signal.value.status_code == 404

    monkeypatch.setattr(service, "get_coin_backtests", missing_payload.__get__(service, SignalQueryService))
    with pytest.raises(HTTPException) as missing_backtests:
        await read_coin_backtests("BTCUSD_EVT", service=service)
    assert missing_backtests.value.status_code == 404

    async def decision_payload(self, *_args, **_kwargs):
        del self
        return {"coin_id": 1, "symbol": "BTCUSD_EVT", "canonical_decision": "BUY", "items": []}

    async def market_decision_payload(self, *_args, **_kwargs):
        del self
        return {"coin_id": 1, "symbol": "BTCUSD_EVT", "canonical_decision": "BUY", "items": []}

    async def final_signal_payload(self, *_args, **_kwargs):
        del self
        return {"coin_id": 1, "symbol": "BTCUSD_EVT", "canonical_decision": "BUY", "items": []}

    async def backtests_payload(self, *_args, **_kwargs):
        del self
        return {"coin_id": 1, "symbol": "BTCUSD_EVT", "items": []}

    monkeypatch.setattr(service, "get_coin_decision", decision_payload.__get__(service, SignalQueryService))
    monkeypatch.setattr(
        service,
        "get_coin_market_decision",
        market_decision_payload.__get__(service, SignalQueryService),
    )
    monkeypatch.setattr(
        service,
        "get_coin_final_signal",
        final_signal_payload.__get__(service, SignalQueryService),
    )
    monkeypatch.setattr(service, "get_coin_backtests", backtests_payload.__get__(service, SignalQueryService))

    assert (await read_coin_decision("BTCUSD_EVT", service=service)).symbol == "BTCUSD_EVT"
    market_decision = await read_coin_market_decision(
        "BTCUSD_EVT",
        request=SimpleNamespace(headers={}),
        response=Response(),
        service=service,
    )
    assert market_decision.symbol == "BTCUSD_EVT"
    assert (await read_coin_final_signal("BTCUSD_EVT", service=service)).symbol == "BTCUSD_EVT"
    assert (await read_coin_backtests("BTCUSD_EVT", service=service)).symbol == "BTCUSD_EVT"


def test_signals_api_router_is_mode_agnostic_and_legacy_views_removed() -> None:
    full_router = build_signals_router(mode=LaunchMode.FULL, profile=DeploymentProfile.PLATFORM_FULL)
    ha_router = build_signals_router(mode=LaunchMode.HA_ADDON, profile=DeploymentProfile.HA_EMBEDDED)

    full_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in full_router.routes}
    ha_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in ha_router.routes}

    assert full_paths == ha_paths
    assert any(path == "/signals" and "GET" in methods for path, methods in full_paths)
    assert any(path == "/coins/{symbol}/decision" and "GET" in methods for path, methods in full_paths)
    assert any(path == "/strategies/performance" and "GET" in methods for path, methods in full_paths)
    assert importlib.util.find_spec("src.apps.signals.views") is None
