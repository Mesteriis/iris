from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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
    assert missing_decision_response.json()["detail"] == "Coin 'MISSING_EVT' was not found."

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
    assert coin_market_decision_response.json() == {
        "coin_id": seeded_api_state["btc"].id,
        "symbol": "BTCUSD_EVT",
        "canonical_decision": "BUY",
        "items": [
            {
                "timeframe": 15,
                "decision": "BUY",
                "confidence": 0.998,
                "signal_count": 3,
                "regime": "bull_trend",
                "created_at": json_utc(seeded_api_state["signal_timestamp"]),
            }
        ],
    }

    missing_market_decision_response = await client.get("/coins/MISSING_EVT/market-decision")
    assert missing_market_decision_response.status_code == 404
    assert missing_market_decision_response.json()["detail"] == "Coin 'MISSING_EVT' was not found."

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
    assert missing_final_signal_response.json()["detail"] == "Coin 'MISSING_EVT' was not found."

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
    assert missing_backtests_response.json()["detail"] == "Coin 'MISSING_EVT' was not found."

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
    from app.apps.signals.views import read_coin_backtests, read_coin_decision, read_coin_final_signal, read_coin_market_decision

    async def missing_payload(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.apps.signals.views.get_coin_decision_async", missing_payload)
    with pytest.raises(HTTPException) as missing_decision:
        await read_coin_decision("BTCUSD_EVT", db=object())
    assert missing_decision.value.status_code == 404

    monkeypatch.setattr("app.apps.signals.views.get_coin_market_decision_async", missing_payload)
    with pytest.raises(HTTPException) as missing_market_decision:
        await read_coin_market_decision("BTCUSD_EVT", db=object())
    assert missing_market_decision.value.status_code == 404

    monkeypatch.setattr("app.apps.signals.views.get_coin_final_signal_async", missing_payload)
    with pytest.raises(HTTPException) as missing_final_signal:
        await read_coin_final_signal("BTCUSD_EVT", db=object())
    assert missing_final_signal.value.status_code == 404

    monkeypatch.setattr("app.apps.signals.views.get_coin_backtests_async", missing_payload)
    with pytest.raises(HTTPException) as missing_backtests:
        await read_coin_backtests("BTCUSD_EVT", db=object())
    assert missing_backtests.value.status_code == 404

    async def decision_payload(*_args, **_kwargs):
        return {"coin_id": 1, "symbol": "BTCUSD_EVT", "canonical_decision": "BUY", "items": []}

    async def market_decision_payload(*_args, **_kwargs):
        return {"coin_id": 1, "symbol": "BTCUSD_EVT", "canonical_decision": "BUY", "items": []}

    async def final_signal_payload(*_args, **_kwargs):
        return {"coin_id": 1, "symbol": "BTCUSD_EVT", "canonical_decision": "BUY", "items": []}

    async def backtests_payload(*_args, **_kwargs):
        return {"coin_id": 1, "symbol": "BTCUSD_EVT", "items": []}

    monkeypatch.setattr("app.apps.signals.views.get_coin_decision_async", decision_payload)
    monkeypatch.setattr("app.apps.signals.views.get_coin_market_decision_async", market_decision_payload)
    monkeypatch.setattr("app.apps.signals.views.get_coin_final_signal_async", final_signal_payload)
    monkeypatch.setattr("app.apps.signals.views.get_coin_backtests_async", backtests_payload)

    assert (await read_coin_decision("BTCUSD_EVT", db=object())).symbol == "BTCUSD_EVT"
    assert (await read_coin_market_decision("BTCUSD_EVT", db=object())).symbol == "BTCUSD_EVT"
    assert (await read_coin_final_signal("BTCUSD_EVT", db=object())).symbol == "BTCUSD_EVT"
    assert (await read_coin_backtests("BTCUSD_EVT", db=object())).symbol == "BTCUSD_EVT"
