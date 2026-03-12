from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

import app.apps.signals.cache as signal_cache_module
import app.apps.signals.market_decision_selectors as market_selector_module
import app.apps.signals.services as signal_services_module
from app.apps.patterns.selectors import _signal_select
from app.apps.signals.cache import (
    DECISION_CACHE_TTL_SECONDS,
    DecisionCacheEntry,
    _parse_decision_payload,
    cache_market_decision_snapshot,
    cache_market_decision_snapshot_async,
    decision_cache_key,
    get_async_decision_cache_client,
    get_decision_cache_client,
    read_cached_market_decision,
    read_cached_market_decision_async,
)
from app.apps.signals.decision_selectors import get_coin_decision, list_decisions, list_top_decisions
from app.apps.signals.final_signal_selectors import get_coin_final_signal, list_final_signals, list_top_final_signals
from app.apps.signals.market_decision_selectors import get_coin_market_decision, list_market_decisions, list_top_market_decisions
from app.apps.signals.models import FinalSignal, InvestmentDecision, Strategy, StrategyRule
from app.apps.signals.services import (
    _cluster_membership_map_async,
    _serialize_signal_rows_async,
    get_coin_backtests_async,
    get_coin_decision_async,
    get_coin_final_signal_async,
    get_coin_market_decision_async,
    list_backtests_async,
    list_decisions_async,
    list_enriched_signals_async,
    list_final_signals_async,
    list_market_decisions_async,
    list_strategies_async,
    list_strategy_performance_async,
    list_top_backtests_async,
    list_top_decisions_async,
    list_top_final_signals_async,
    list_top_market_decisions_async,
    list_top_signals_async,
)
from app.apps.signals.strategies import list_strategies, list_strategy_performance
from tests.factories.seeds import DecisionSeedFactory, StrategySeedFactory


class _SyncCacheClient:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.last_ex: int | None = None

    def set(self, key: str, value: str, *, ex: int) -> None:
        self.storage[key] = value
        self.last_ex = ex

    def get(self, key: str) -> str | None:
        return self.storage.get(key)


class _AsyncCacheClient:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.last_ex: int | None = None

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.storage[key] = value
        self.last_ex = ex

    async def get(self, key: str) -> str | None:
        return self.storage.get(key)


def test_signals_cache_round_trip_and_parse_guards(monkeypatch, settings, seeded_api_state) -> None:
    sync_client = _SyncCacheClient()
    async_client = _AsyncCacheClient()

    get_decision_cache_client.cache_clear()
    get_async_decision_cache_client.cache_clear()
    monkeypatch.setattr(signal_cache_module.Redis, "from_url", staticmethod(lambda url, decode_responses: (url, decode_responses)))
    monkeypatch.setattr(signal_cache_module.AsyncRedis, "from_url", staticmethod(lambda url, decode_responses: (url, decode_responses)))
    assert get_decision_cache_client() == (settings.redis_url, True)
    assert get_async_decision_cache_client() == (settings.redis_url, True)
    get_decision_cache_client.cache_clear()
    get_async_decision_cache_client.cache_clear()

    monkeypatch.setattr(signal_cache_module, "get_decision_cache_client", lambda: sync_client)
    monkeypatch.setattr(signal_cache_module, "get_async_decision_cache_client", lambda: async_client)

    timestamp = seeded_api_state["signal_timestamp"]
    cache_market_decision_snapshot(
        coin_id=11,
        timeframe=15,
        decision="BUY",
        confidence=0.91,
        signal_count=4,
        regime="bull_trend",
        created_at=timestamp,
    )
    assert sync_client.last_ex == DECISION_CACHE_TTL_SECONDS
    sync_entry = read_cached_market_decision(coin_id=11, timeframe=15)
    assert sync_entry is not None
    assert sync_entry.decision == "BUY"
    assert sync_entry.created_at == timestamp
    assert read_cached_market_decision(coin_id=99, timeframe=60) is None

    async def _async_round_trip() -> None:
        await cache_market_decision_snapshot_async(
            coin_id=12,
            timeframe=60,
            decision="HOLD",
            confidence=0.52,
            signal_count=2,
            regime=None,
            created_at=timestamp,
        )
        assert async_client.last_ex == DECISION_CACHE_TTL_SECONDS
        async_entry = await read_cached_market_decision_async(coin_id=12, timeframe=60)
        assert async_entry is not None
        assert async_entry.decision == "HOLD"
        assert async_entry.regime is None
        assert await read_cached_market_decision_async(coin_id=777, timeframe=240) is None

    asyncio.run(_async_round_trip())

    payload = _parse_decision_payload("{", fallback_coin_id=1, fallback_timeframe=15)
    assert payload is None
    assert _parse_decision_payload(json.dumps({"decision": 7}), fallback_coin_id=1, fallback_timeframe=15) is None

    parsed = _parse_decision_payload(
        json.dumps(
            {
                "decision": "SELL",
                "confidence": "bad",
                "signal_count": "bad",
                "regime": ["bad"],
                "created_at": "not-a-date",
            }
        ),
        fallback_coin_id=91,
        fallback_timeframe=240,
    )
    assert parsed is not None
    assert parsed.coin_id == 91
    assert parsed.timeframe == 240
    assert parsed.confidence == 0.0
    assert parsed.signal_count == 0
    assert parsed.regime is None
    assert parsed.created_at is None
    parsed_without_datetime = _parse_decision_payload(
        json.dumps({"decision": "HOLD", "created_at": 123, "regime": "bull_trend"}),
        fallback_coin_id=92,
        fallback_timeframe=60,
    )
    assert parsed_without_datetime is not None
    assert parsed_without_datetime.created_at is None
    assert parsed_without_datetime.regime == "bull_trend"

    assert decision_cache_key(7, 15) == "iris:decision:7:15"


def test_signal_sync_selectors_and_strategies_cover_cached_and_db_paths(db_session, seeded_api_state, monkeypatch) -> None:
    btc = seeded_api_state["btc"]
    eth = seeded_api_state["eth"]
    timestamp = seeded_api_state["signal_timestamp"]

    extra_final = FinalSignal(
        coin_id=int(eth.id),
        timeframe=60,
        decision="HOLD",
        confidence=0.41,
        risk_adjusted_score=45.2,
        reason="Range-bound market",
        created_at=timestamp + timedelta(minutes=5),
    )
    disabled_strategy_seed = StrategySeedFactory.build(created_at=timestamp + timedelta(minutes=3))
    disabled_strategy = Strategy(
        name=disabled_strategy_seed.name,
        description=disabled_strategy_seed.description,
        enabled=False,
        created_at=disabled_strategy_seed.created_at,
    )
    disabled_rule = StrategyRule(
        strategy=disabled_strategy,
        pattern_slug="breakout_retest",
        regime="sideways_range",
        sector="smart_contract",
        cycle="accumulation",
        min_confidence=0.58,
    )
    db_session.add_all([extra_final, disabled_strategy, disabled_rule])
    db_session.commit()

    decisions = list_decisions(db_session, symbol="btcusd_evt", timeframe=15, limit=0)
    assert len(decisions) == 1
    assert decisions[0]["sector"] == "store_of_value"
    assert list_decisions(db_session, symbol="BTCUSD_EVT", limit=10)
    assert list_decisions(db_session, timeframe=15, limit=10)
    top_decisions = list_top_decisions(db_session, limit=200)
    assert any(row["symbol"] == "BTCUSD_EVT" and row["decision"] == "BUY" for row in top_decisions)
    coin_decision = get_coin_decision(db_session, "BTCUSD_EVT")
    assert coin_decision is not None
    assert coin_decision["canonical_decision"] == "BUY"
    empty_coin_decision = get_coin_decision(db_session, "ETHUSD_EVT")
    assert empty_coin_decision is not None
    assert empty_coin_decision["canonical_decision"] is None
    assert empty_coin_decision["items"] == []
    assert get_coin_decision(db_session, "MISSING_EVT") is None

    market_rows = list_market_decisions(db_session, symbol="ETHUSD_EVT", timeframe=60, limit=10)
    assert [row["symbol"] for row in market_rows] == ["ETHUSD_EVT"]
    assert list_market_decisions(db_session, symbol="ETHUSD_EVT", limit=10)
    assert list_market_decisions(db_session, timeframe=60, limit=10)
    top_market_rows = list_top_market_decisions(db_session, limit=200)
    assert any(row["symbol"] == "BTCUSD_EVT" and row["decision"] == "BUY" for row in top_market_rows)

    cached_entries = {
        1440: DecisionCacheEntry(
            coin_id=int(btc.id),
            timeframe=1440,
            decision="STRONG_BUY",
            confidence=0.97,
            signal_count=9,
            regime=None,
            created_at=timestamp,
        ),
        15: DecisionCacheEntry(
            coin_id=int(btc.id),
            timeframe=15,
            decision="BUY",
            confidence=0.83,
            signal_count=3,
            regime=None,
            created_at=timestamp,
        ),
    }
    monkeypatch.setattr(
        market_selector_module,
        "read_cached_market_decision",
        lambda *, coin_id, timeframe: cached_entries.get(timeframe) if coin_id == int(btc.id) else None,
    )
    cached_market = get_coin_market_decision(db_session, "BTCUSD_EVT")
    assert cached_market is not None
    assert cached_market["canonical_decision"] == "STRONG_BUY"
    assert [row["timeframe"] for row in cached_market["items"]] == [15, 1440]
    assert {row["regime"] for row in cached_market["items"]} == {"bull_trend"}

    monkeypatch.setattr(market_selector_module, "read_cached_market_decision", lambda **_: None)
    fallback_market = get_coin_market_decision(db_session, "ETHUSD_EVT")
    assert fallback_market is not None
    assert fallback_market["canonical_decision"] == "HOLD"
    assert fallback_market["items"][0]["regime"] == "sideways_range"
    empty_sync_market = get_coin_market_decision(db_session, "SOLUSD_EVT")
    assert empty_sync_market is not None
    assert empty_sync_market["canonical_decision"] is None
    assert empty_sync_market["items"] == []
    assert get_coin_market_decision(db_session, "MISSING_EVT") is None

    final_rows = list_final_signals(db_session, symbol="ETHUSD_EVT", timeframe=60, limit=10)
    assert [row["symbol"] for row in final_rows] == ["ETHUSD_EVT"]
    final_rows = list_final_signals(db_session, limit=200)
    assert {"BTCUSD_EVT", "ETHUSD_EVT"} <= {row["symbol"] for row in final_rows}
    top_final_rows = list_top_final_signals(db_session, limit=200)
    assert any(row["symbol"] == "BTCUSD_EVT" and row["risk_adjusted_score"] == 99.69 for row in top_final_rows)
    btc_final = get_coin_final_signal(db_session, "BTCUSD_EVT")
    assert btc_final is not None
    assert btc_final["items"][0]["liquidity_score"] == 0.87
    eth_final = get_coin_final_signal(db_session, "ETHUSD_EVT")
    assert eth_final is not None
    assert eth_final["items"][0]["liquidity_score"] == 0.0
    empty_final = get_coin_final_signal(db_session, "SOLUSD_EVT")
    assert empty_final is not None
    assert empty_final["canonical_decision"] is None
    assert empty_final["items"] == []
    assert get_coin_final_signal(db_session, "MISSING_EVT") is None

    enabled_strategies = list_strategies(db_session, enabled_only=True, limit=10)
    assert [row["id"] for row in enabled_strategies] == [101]
    all_strategies = list_strategies(db_session, enabled_only=False, limit=10)
    assert {row["name"] for row in all_strategies} >= {"Momentum Breakout", disabled_strategy_seed.name}
    assert next(row for row in all_strategies if row["name"] == disabled_strategy_seed.name)["performance"] is None
    performance = list_strategy_performance(db_session, limit=0)
    assert performance[0]["strategy_id"] == 101


@pytest.mark.asyncio
async def test_signal_async_services_cover_selectors_serialization_and_strategy_paths(async_db_session, seeded_api_state, monkeypatch) -> None:
    btc = seeded_api_state["btc"]
    eth = seeded_api_state["eth"]
    timestamp = seeded_api_state["signal_timestamp"]

    rows = (
        await async_db_session.execute(
            _signal_select()
            .where(signal_services_module.Signal.coin_id == int(btc.id), signal_services_module.Signal.timeframe == 15)
            .order_by(signal_services_module.Signal.candle_timestamp.desc(), signal_services_module.Signal.created_at.desc())
        )
    ).all()
    assert await _cluster_membership_map_async(async_db_session, []) == {}
    membership = await _cluster_membership_map_async(async_db_session, rows)
    assert membership[(int(btc.id), 15, timestamp)] == ["pattern_cluster_breakout"]

    serialized = await _serialize_signal_rows_async(async_db_session, rows)
    assert serialized[0]["cluster_membership"] == ["pattern_cluster_breakout"]
    assert serialized[0]["market_regime"] == "bull_trend"
    assert serialized[0]["cycle_phase"] == "markup"

    enriched = await list_enriched_signals_async(async_db_session, symbol="BTCUSD_EVT", timeframe=15, limit=10)
    assert [row["signal_type"] for row in enriched] == ["pattern_bull_flag", "pattern_cluster_breakout"]
    assert await list_enriched_signals_async(async_db_session, symbol="BTCUSD_EVT", limit=10)
    assert await list_enriched_signals_async(async_db_session, timeframe=15, limit=10)
    top_signals = await list_top_signals_async(async_db_session, limit=200)
    assert any(row["symbol"] == "BTCUSD_EVT" and row["signal_type"] == "pattern_bull_flag" for row in top_signals)

    extra_decision_seed = DecisionSeedFactory.build(decision="ACCUMULATE", created_at=timestamp + timedelta(minutes=2))
    extra_investment = InvestmentDecision(
        coin_id=int(btc.id),
        timeframe=1440,
        decision=extra_decision_seed.decision,
        confidence=extra_decision_seed.confidence,
        score=102.4,
        reason="Higher timeframe consensus",
        created_at=extra_decision_seed.created_at,
    )
    extra_final = FinalSignal(
        coin_id=int(eth.id),
        timeframe=60,
        decision="HOLD",
        confidence=0.43,
        risk_adjusted_score=41.7,
        reason="No clean risk/reward",
        created_at=timestamp + timedelta(minutes=4),
    )
    disabled_strategy_seed = StrategySeedFactory.build(created_at=timestamp + timedelta(minutes=6))
    disabled_strategy = Strategy(
        name=disabled_strategy_seed.name,
        description=disabled_strategy_seed.description,
        enabled=False,
        created_at=disabled_strategy_seed.created_at,
    )
    disabled_rule = StrategyRule(
        strategy=disabled_strategy,
        pattern_slug="breakout_retest",
        regime="sideways_range",
        sector="smart_contract",
        cycle="accumulation",
        min_confidence=0.55,
    )
    async_db_session.add_all([extra_investment, extra_final, disabled_strategy, disabled_rule])
    await async_db_session.commit()

    decisions = await list_decisions_async(async_db_session, symbol="BTCUSD_EVT", limit=10)
    assert {row["timeframe"] for row in decisions} == {15, 1440}
    assert await list_decisions_async(async_db_session, timeframe=15, limit=10)
    top_decisions = await list_top_decisions_async(async_db_session, limit=200)
    assert any(row["symbol"] == "BTCUSD_EVT" and row["timeframe"] == 1440 for row in top_decisions)
    btc_decision = await get_coin_decision_async(async_db_session, "BTCUSD_EVT")
    assert btc_decision is not None
    assert btc_decision["canonical_decision"] == "ACCUMULATE"
    eth_decision = await get_coin_decision_async(async_db_session, "ETHUSD_EVT")
    assert eth_decision is not None
    assert eth_decision["canonical_decision"] is None
    assert eth_decision["items"] == []
    assert await get_coin_decision_async(async_db_session, "MISSING_EVT") is None

    cached_entries = {
        1440: DecisionCacheEntry(
            coin_id=int(btc.id),
            timeframe=1440,
            decision="SELL",
            confidence=0.73,
            signal_count=11,
            regime=None,
            created_at=timestamp + timedelta(minutes=1),
        ),
        15: DecisionCacheEntry(
            coin_id=int(btc.id),
            timeframe=15,
            decision="BUY",
            confidence=0.98,
            signal_count=3,
            regime="bull_trend",
            created_at=timestamp,
        ),
    }

    async def _cached_reader(*, coin_id: int, timeframe: int):
        if coin_id != int(btc.id):
            return None
        return cached_entries.get(timeframe)

    monkeypatch.setattr(signal_services_module, "read_cached_market_decision_async", _cached_reader)
    cached_market = await get_coin_market_decision_async(async_db_session, "BTCUSD_EVT")
    assert cached_market is not None
    assert cached_market["canonical_decision"] == "SELL"
    assert [row["timeframe"] for row in cached_market["items"]] == [15, 1440]

    async def _empty_reader(*, coin_id: int, timeframe: int):
        return None

    monkeypatch.setattr(signal_services_module, "read_cached_market_decision_async", _empty_reader)
    market_rows = await list_market_decisions_async(async_db_session, symbol="ETHUSD_EVT", timeframe=60, limit=10)
    assert [row["symbol"] for row in market_rows] == ["ETHUSD_EVT"]
    assert await list_market_decisions_async(async_db_session, symbol="ETHUSD_EVT", limit=10)
    assert await list_market_decisions_async(async_db_session, timeframe=60, limit=10)
    top_market_rows = await list_top_market_decisions_async(async_db_session, limit=200)
    assert any(row["symbol"] == "BTCUSD_EVT" and row["decision"] == "BUY" for row in top_market_rows)
    fallback_market = await get_coin_market_decision_async(async_db_session, "ETHUSD_EVT")
    assert fallback_market is not None
    assert fallback_market["canonical_decision"] == "HOLD"
    empty_market = await get_coin_market_decision_async(async_db_session, "SOLUSD_EVT")
    assert empty_market is not None
    assert empty_market["canonical_decision"] is None
    assert empty_market["items"] == []
    assert await get_coin_market_decision_async(async_db_session, "MISSING_EVT") is None

    final_rows = await list_final_signals_async(async_db_session, symbol="ETHUSD_EVT", timeframe=60, limit=10)
    assert [row["symbol"] for row in final_rows] == ["ETHUSD_EVT"]
    final_rows = await list_final_signals_async(async_db_session, limit=200)
    assert {"BTCUSD_EVT", "ETHUSD_EVT"} <= {row["symbol"] for row in final_rows}
    top_final_rows = await list_top_final_signals_async(async_db_session, limit=200)
    assert any(row["symbol"] == "BTCUSD_EVT" and row["risk_adjusted_score"] == 99.69 for row in top_final_rows)
    eth_final = await get_coin_final_signal_async(async_db_session, "ETHUSD_EVT")
    assert eth_final is not None
    assert eth_final["items"][0]["volatility_risk"] == 0.0
    empty_async_final = await get_coin_final_signal_async(async_db_session, "SOLUSD_EVT")
    assert empty_async_final is not None
    assert empty_async_final["canonical_decision"] is None
    assert empty_async_final["items"] == []
    assert await get_coin_final_signal_async(async_db_session, "MISSING_EVT") is None

    backtests = await list_backtests_async(
        async_db_session,
        symbol="BTCUSD_EVT",
        timeframe=15,
        signal_type="pattern_bull_flag",
        limit=0,
    )
    assert len(backtests) == 1
    assert backtests[0]["sample_size"] == 2
    assert await list_backtests_async(async_db_session, symbol="BTCUSD_EVT", limit=10)
    assert await list_backtests_async(async_db_session, timeframe=15, limit=10)
    top_backtests = await list_top_backtests_async(async_db_session, timeframe=15, limit=200)
    assert any(row["signal_type"] == "pattern_bull_flag" and row["timeframe"] == 15 for row in top_backtests)
    coin_backtests = await get_coin_backtests_async(
        async_db_session,
        "BTCUSD_EVT",
        timeframe=15,
        signal_type="pattern_bull_flag",
        limit=0,
    )
    assert coin_backtests is not None
    assert coin_backtests["items"][0]["coin_count"] == 1
    assert await get_coin_backtests_async(async_db_session, "MISSING_EVT") is None

    enabled_strategies = await list_strategies_async(async_db_session, enabled_only=True, limit=10)
    assert [row["id"] for row in enabled_strategies] == [101]
    all_strategies = await list_strategies_async(async_db_session, enabled_only=False, limit=10)
    assert any(row["performance"] is None for row in all_strategies)
    strategy_performance = await list_strategy_performance_async(async_db_session, limit=0)
    assert strategy_performance[0]["strategy_id"] == 101
