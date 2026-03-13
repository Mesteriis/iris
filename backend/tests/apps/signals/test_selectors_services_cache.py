from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

import src.apps.signals.cache as signal_cache_module
import src.apps.signals.query_services as signal_query_module
from src.apps.patterns.query_builders import signal_select as _signal_select
from src.apps.signals.cache import (
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
from src.apps.signals.models import FinalSignal, InvestmentDecision, Signal, Strategy, StrategyRule
from src.apps.signals.query_services import (
    SignalQueryService,
    _cluster_membership_map_async,
    _serialize_signal_rows_async,
)
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

@pytest.mark.asyncio
async def test_signal_async_services_cover_selectors_serialization_and_strategy_paths(async_db_session, seeded_api_state, monkeypatch) -> None:
    btc = seeded_api_state["btc"]
    eth = seeded_api_state["eth"]
    timestamp = seeded_api_state["signal_timestamp"]
    query_service = SignalQueryService(async_db_session)

    rows = (
        await async_db_session.execute(
            _signal_select()
            .where(Signal.coin_id == int(btc.id), Signal.timeframe == 15)
            .order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc())
        )
    ).all()
    assert await _cluster_membership_map_async(async_db_session, []) == {}
    membership = await _cluster_membership_map_async(async_db_session, rows)
    assert membership[(int(btc.id), 15, timestamp)] == ["pattern_cluster_breakout"]

    serialized = await _serialize_signal_rows_async(async_db_session, rows)
    assert serialized[0].cluster_membership == ("pattern_cluster_breakout",)
    assert serialized[0].market_regime == "bull_trend"
    assert serialized[0].cycle_phase == "markup"

    enriched = await query_service.list_signals(symbol="BTCUSD_EVT", timeframe=15, limit=10)
    assert [row.signal_type for row in enriched] == ["pattern_bull_flag", "pattern_cluster_breakout"]
    assert await query_service.list_signals(symbol="BTCUSD_EVT", limit=10)
    assert await query_service.list_signals(timeframe=15, limit=10)
    top_signals = await query_service.list_top_signals(limit=200)
    assert any(row.symbol == "BTCUSD_EVT" and row.signal_type == "pattern_bull_flag" for row in top_signals)

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

    decisions = await query_service.list_decisions(symbol="BTCUSD_EVT", limit=10)
    assert {row.timeframe for row in decisions} == {15, 1440}
    assert await query_service.list_decisions(timeframe=15, limit=10)
    top_decisions = await query_service.list_top_decisions(limit=200)
    assert any(row.symbol == "BTCUSD_EVT" and row.timeframe == 1440 for row in top_decisions)
    btc_decision = await query_service.get_coin_decision("BTCUSD_EVT")
    assert btc_decision is not None
    assert btc_decision.canonical_decision == "ACCUMULATE"
    eth_decision = await query_service.get_coin_decision("ETHUSD_EVT")
    assert eth_decision is not None
    assert eth_decision.canonical_decision is None
    assert eth_decision.items == ()
    assert await query_service.get_coin_decision("MISSING_EVT") is None

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

    monkeypatch.setattr(signal_query_module, "read_cached_market_decision_async", _cached_reader)
    cached_market = await query_service.get_coin_market_decision("BTCUSD_EVT")
    assert cached_market is not None
    assert cached_market.canonical_decision == "SELL"
    assert [row.timeframe for row in cached_market.items] == [15, 1440]

    async def _empty_reader(*, coin_id: int, timeframe: int):
        return None

    monkeypatch.setattr(signal_query_module, "read_cached_market_decision_async", _empty_reader)
    market_rows = await query_service.list_market_decisions(symbol="ETHUSD_EVT", timeframe=60, limit=10)
    assert [row.symbol for row in market_rows] == ["ETHUSD_EVT"]
    assert await query_service.list_market_decisions(symbol="ETHUSD_EVT", limit=10)
    assert await query_service.list_market_decisions(timeframe=60, limit=10)
    top_market_rows = await query_service.list_top_market_decisions(limit=200)
    assert any(row.symbol == "BTCUSD_EVT" and row.decision == "BUY" for row in top_market_rows)
    fallback_market = await query_service.get_coin_market_decision("ETHUSD_EVT")
    assert fallback_market is not None
    assert fallback_market.canonical_decision == "HOLD"
    empty_market = await query_service.get_coin_market_decision("SOLUSD_EVT")
    assert empty_market is not None
    assert empty_market.canonical_decision is None
    assert empty_market.items == ()
    assert await query_service.get_coin_market_decision("MISSING_EVT") is None

    final_rows = await query_service.list_final_signals(symbol="ETHUSD_EVT", timeframe=60, limit=10)
    assert [row.symbol for row in final_rows] == ["ETHUSD_EVT"]
    final_rows = await query_service.list_final_signals(limit=200)
    assert {"BTCUSD_EVT", "ETHUSD_EVT"} <= {row.symbol for row in final_rows}
    top_final_rows = await query_service.list_top_final_signals(limit=200)
    assert any(row.symbol == "BTCUSD_EVT" and row.risk_adjusted_score == 99.69 for row in top_final_rows)
    eth_final = await query_service.get_coin_final_signal("ETHUSD_EVT")
    assert eth_final is not None
    assert eth_final.items[0].volatility_risk == 0.0
    empty_async_final = await query_service.get_coin_final_signal("SOLUSD_EVT")
    assert empty_async_final is not None
    assert empty_async_final.canonical_decision is None
    assert empty_async_final.items == ()
    assert await query_service.get_coin_final_signal("MISSING_EVT") is None

    backtests = await query_service.list_backtests(
        symbol="BTCUSD_EVT",
        timeframe=15,
        signal_type="pattern_bull_flag",
        limit=0,
    )
    assert len(backtests) == 1
    assert backtests[0].sample_size == 2
    assert await query_service.list_backtests(symbol="BTCUSD_EVT", limit=10)
    assert await query_service.list_backtests(timeframe=15, limit=10)
    top_backtests = await query_service.list_top_backtests(timeframe=15, limit=200)
    assert any(row.signal_type == "pattern_bull_flag" and row.timeframe == 15 for row in top_backtests)
    coin_backtests = await query_service.get_coin_backtests(
        "BTCUSD_EVT",
        timeframe=15,
        signal_type="pattern_bull_flag",
        limit=0,
    )
    assert coin_backtests is not None
    assert coin_backtests.items[0].coin_count == 1
    assert await query_service.get_coin_backtests("MISSING_EVT") is None

    enabled_strategies = await query_service.list_strategies(enabled_only=True, limit=10)
    assert [row.id for row in enabled_strategies] == [101]
    all_strategies = await query_service.list_strategies(enabled_only=False, limit=10)
    assert any(row.performance is None for row in all_strategies)
    strategy_performance = await query_service.list_strategy_performance(limit=0)
    assert strategy_performance[0].strategy_id == 101
