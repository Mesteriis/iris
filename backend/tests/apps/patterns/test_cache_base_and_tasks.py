from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.apps.market_data.repos import CandlePoint
from app.apps.patterns import cache, tasks
from app.apps.patterns.domain.base import PatternDetector
from app.apps.patterns.domain.scheduler import assign_activity_bucket, calculate_activity_score


class _AsyncDbContext:
    def __init__(self, db: object) -> None:
        self.db = db

    async def __aenter__(self) -> object:
        return self.db

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@asynccontextmanager
async def _async_lock(acquired: bool):
    yield acquired


class _SyncCacheClient:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []

    def set(self, key: str, value: str, *, ex: int) -> None:
        self.storage[key] = value
        self.set_calls.append((key, value, ex))

    def get(self, key: str) -> str | None:
        return self.storage.get(key)


class _AsyncCacheClient:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.storage[key] = value
        self.set_calls.append((key, value, ex))

    async def get(self, key: str) -> str | None:
        return self.storage.get(key)


class _BaseProbeDetector(PatternDetector):
    def detect(self, candles, indicators):
        return super().detect(candles, indicators)


def test_patterns_cache_and_base_helpers(monkeypatch) -> None:
    sync_client = _SyncCacheClient()
    async_client = _AsyncCacheClient()

    cache.get_regime_cache_client.cache_clear()
    cache.get_async_regime_cache_client.cache_clear()

    monkeypatch.setattr(cache, "get_regime_cache_client", lambda: sync_client)
    monkeypatch.setattr(cache, "get_async_regime_cache_client", lambda: async_client)

    key = cache.regime_cache_key(coin_id=7, timeframe=60)
    assert key == "iris:regime:7:60"
    payload = cache._serialize_regime_payload(timeframe=60, regime="bull_trend", confidence=0.82)
    assert cache._parse_regime_payload(payload, fallback_timeframe=15).regime == "bull_trend"
    assert cache._parse_regime_payload("{", fallback_timeframe=15) is None
    assert cache._parse_regime_payload('{"timeframe":60}', fallback_timeframe=15) is None
    parsed = cache._parse_regime_payload('{"regime":"range","confidence":"bad"}', fallback_timeframe=15)
    assert parsed is not None and parsed.confidence == 0.0 and parsed.timeframe == 15

    cache.cache_regime_snapshot(coin_id=7, timeframe=60, regime="bull_trend", confidence=0.82)
    assert sync_client.set_calls[0][2] == cache.REGIME_CACHE_TTL_SECONDS
    assert cache.read_cached_regime(coin_id=7, timeframe=60).regime == "bull_trend"
    assert cache.read_cached_regime(coin_id=9, timeframe=60) is None

    async def _async_assertions() -> None:
        await cache.cache_regime_snapshot_async(coin_id=8, timeframe=15, regime="sideways", confidence=0.61)
        cached = await cache.read_cached_regime_async(coin_id=8, timeframe=15)
        assert cached is not None
        assert cached.regime == "sideways"
        assert await cache.read_cached_regime_async(coin_id=99, timeframe=15) is None

    import asyncio

    asyncio.run(_async_assertions())

    detector = _BaseProbeDetector()
    candle = CandlePoint(
        timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
    )
    with pytest.raises(NotImplementedError):
        detector.detect([candle], {})

    assert round(
        calculate_activity_score(
            price_change_24h=12.0,
            volatility=4.0,
            volume_change_24h=30.0,
            price_current=200.0,
        ),
        4,
    ) == 38.0
    assert assign_activity_bucket(80.0) == "HOT"
    assert assign_activity_bucket(45.0) == "WARM"
    assert assign_activity_bucket(20.0) == "COLD"
    assert assign_activity_bucket(1.0) == "DEAD"


@pytest.mark.asyncio
async def test_patterns_tasks_orchestration_branches(monkeypatch) -> None:
    async def run_sync(fn):
        return fn(SimpleNamespace(get=lambda model, coin_id: SimpleNamespace(id=coin_id)))

    db = SimpleNamespace(run_sync=run_sync)
    coin = SimpleNamespace(id=7, symbol="BTCUSD_EVT")

    monkeypatch.setattr(tasks, "AsyncSessionLocal", lambda: _AsyncDbContext(db))
    monkeypatch.setattr(tasks, "async_redis_task_lock", lambda *args, **kwargs: _async_lock(False))

    skipped = await tasks.patterns_bootstrap_scan(symbol="btcusd_evt")
    assert skipped["reason"] == "patterns_bootstrap_in_progress"
    assert (await tasks._run_pattern_evaluation())["reason"] == "pattern_statistics_refresh_in_progress"
    assert (await tasks.refresh_market_structure())["reason"] == "market_structure_refresh_in_progress"
    assert (await tasks.run_pattern_discovery())["reason"] == "pattern_discovery_refresh_in_progress"
    assert (await tasks.strategy_discovery_job())["reason"] == "strategy_discovery_refresh_in_progress"

    monkeypatch.setattr(tasks, "async_redis_task_lock", lambda *args, **kwargs: _async_lock(True))
    monkeypatch.setattr(tasks, "get_coin_by_symbol_async", lambda db, symbol: __import__("asyncio").sleep(0, result=None))
    assert (await tasks.patterns_bootstrap_scan(symbol="btcusd_evt"))["reason"] == "coin_not_found"

    monkeypatch.setattr(tasks, "get_coin_by_symbol_async", lambda db, symbol: __import__("asyncio").sleep(0, result=coin if symbol.upper() == "BTCUSD_EVT" else None))
    monkeypatch.setattr(tasks, "list_coin_symbols_ready_for_latest_sync_async", lambda db: __import__("asyncio").sleep(0, result=["BTCUSD_EVT", "MISSING_EVT"]))
    monkeypatch.setattr(tasks, "_ENGINE", SimpleNamespace(bootstrap_coin=lambda sync_db, coin, force=False: {"coin_id": int(coin.id), "created": 2 if force else 1}))
    bootstrap_one = await tasks.patterns_bootstrap_scan(symbol="btcusd_evt", force=True)
    bootstrap_all = await tasks.patterns_bootstrap_scan()
    assert bootstrap_one == {"status": "ok", "coins": 1, "items": [{"coin_id": 7, "created": 2}]}
    assert bootstrap_all["coins"] == 2
    assert bootstrap_all["created"] == 1

    monkeypatch.setattr(tasks, "run_pattern_evaluation_cycle", lambda sync_db: {"status": "ok", "signals": 3})
    monkeypatch.setattr(tasks, "enrich_signal_context", lambda *args, **kwargs: {"regime": "bull"})
    monkeypatch.setattr(tasks, "evaluate_investment_decision", lambda *args, **kwargs: {"decision": "BUY"})
    monkeypatch.setattr(tasks, "evaluate_final_signal", lambda *args, **kwargs: {"final": "BUY"})
    monkeypatch.setattr(tasks, "refresh_sector_metrics", lambda sync_db: {"sectors": 2})
    monkeypatch.setattr(tasks, "refresh_market_cycles", lambda sync_db: {"cycles": 3})
    monkeypatch.setattr(tasks, "refresh_recent_signal_contexts", lambda sync_db, lookback_days: {"contexts": lookback_days})
    monkeypatch.setattr(tasks, "refresh_investment_decisions", lambda sync_db, lookback_days, emit_events=False: {"decisions": lookback_days, "emit": emit_events})
    monkeypatch.setattr(tasks, "refresh_final_signals", lambda sync_db, lookback_days, emit_events=False: {"final_signals": lookback_days, "emit": emit_events})
    monkeypatch.setattr(tasks, "refresh_discovered_patterns", lambda sync_db: {"patterns": 5})
    monkeypatch.setattr(tasks, "refresh_strategies", lambda sync_db: {"strategies": 4})

    assert await tasks._run_sync_pattern_core(db, lambda sync_db: {"status": "ok"}) == {"status": "ok"}
    assert await tasks._run_pattern_evaluation() == {"status": "ok", "signals": 3}
    assert await tasks.pattern_evaluation_job() == {"status": "ok", "signals": 3}
    assert await tasks.update_pattern_statistics() == {"status": "ok", "signals": 3}

    enriched = await tasks.signal_context_enrichment(coin_id=7, timeframe=15, candle_timestamp="2026-03-12T12:00:00Z")
    assert enriched["context"] == {"regime": "bull"}
    assert enriched["decision"] == {"decision": "BUY"}
    assert enriched["final_signal"] == {"final": "BUY"}

    structure = await tasks.refresh_market_structure()
    discovery = await tasks.run_pattern_discovery()
    strategy = await tasks.strategy_discovery_job()
    assert structure["status"] == "ok"
    assert discovery == {"patterns": 5}
    assert strategy["strategies"] == {"strategies": 4}
