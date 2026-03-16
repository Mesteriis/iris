from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from src.apps.market_data import tasks


@asynccontextmanager
async def _async_lock(acquired: bool):
    yield acquired


class _AsyncDbContext:
    def __init__(self, db: object) -> None:
        self.db = SimpleNamespace(session=db)

        async def _commit() -> None:
            return None

        self.db.commit = _commit

    async def __aenter__(self) -> object:
        return self.db

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.mark.asyncio
async def test_market_data_tasks_helpers_and_wrappers(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    lock_calls: list[tuple[str, int]] = []
    db = object()

    async def fake_due(self) -> datetime:
        return datetime(2026, 3, 12, 12, 0, tzinfo=UTC)

    async def fake_kiq(**kwargs) -> None:
        calls.append(("patterns", kwargs))

    def fake_lock(key: str, *, timeout: int):
        lock_calls.append((key, timeout))
        return _async_lock(True)

    monkeypatch.setattr(tasks, "AsyncUnitOfWork", lambda: _AsyncDbContext(db))
    monkeypatch.setattr(tasks.MarketDataQueryService, "get_next_pending_backfill_due_at", fake_due)
    monkeypatch.setattr(tasks.patterns_bootstrap_scan, "kiq", fake_kiq)
    monkeypatch.setattr(tasks, "async_redis_task_lock", fake_lock)

    assert await tasks.get_next_history_backfill_due_at() == datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
    async with tasks._with_coin_history_lock("btcusd"):
        pass
    queued = await tasks._enqueue_patterns_bootstrap(symbol="btcusd", force=True)
    assert lock_calls == [("iris:tasklock:history_coin:BTCUSD", tasks.COIN_HISTORY_LOCK_TIMEOUT_SECONDS)]
    assert queued == {"status": "queued", "queue": "analytics", "symbol": "BTCUSD", "force": True}
    assert calls == [("patterns", {"symbol": "btcusd", "force": True})]


@pytest.mark.asyncio
async def test_market_data_tasks_item_level_branches(monkeypatch) -> None:
    coin = SimpleNamespace(symbol="BTCUSD_EVT")
    async def _commit() -> None:
        return None

    uow = SimpleNamespace(session=object(), commit=_commit)

    monkeypatch.setattr(tasks, "_with_coin_history_lock", lambda symbol: _async_lock(False))
    skipped_backfill = await tasks._sync_coin_backfill_item(uow, coin)
    skipped_latest = await tasks._sync_coin_latest_item(uow, coin)
    assert skipped_backfill["reason"] == "coin_history_in_progress"
    assert skipped_latest["reason"] == "coin_history_in_progress"

    patterns_calls: list[dict[str, object]] = []
    monkeypatch.setattr(tasks, "_with_coin_history_lock", lambda symbol: _async_lock(True))

    async def fake_backfill(self, *, symbol: str, force: bool = False):
        return {"symbol": symbol, "created": 4 if force else 3, "status": "ok"}

    monkeypatch.setattr(
        tasks,
        "_enqueue_patterns_bootstrap",
        lambda **kwargs: __import__("asyncio").sleep(0, result=patterns_calls.append(kwargs) or {"status": "queued"}),
    )

    async def fake_latest(self, *, symbol: str, force: bool = False):
        return {"symbol": symbol, "created": 1, "status": "ok"}

    monkeypatch.setattr(tasks.MarketDataHistorySyncService, "sync_coin_history_backfill", fake_backfill)
    monkeypatch.setattr(tasks.MarketDataHistorySyncService, "sync_coin_latest_history", fake_latest)

    backfill = await tasks._sync_coin_backfill_item(uow, coin)
    forced_backfill = await tasks._sync_coin_backfill_item(uow, coin, force=True)
    latest = await tasks._sync_coin_latest_item(uow, coin, force=True)

    assert backfill["patterns_bootstrap"] == {"status": "queued"}
    assert forced_backfill["created"] == 4
    assert latest["created"] == 1
    assert patterns_calls == [{"symbol": "BTCUSD_EVT", "force": False}, {"symbol": "BTCUSD_EVT", "force": True}]

    async def fake_backoff(self, *, symbol: str, force: bool = False):
        return {"symbol": symbol, "created": 0, "status": "backoff"}

    monkeypatch.setattr(tasks.MarketDataHistorySyncService, "sync_coin_history_backfill", fake_backoff)
    no_bootstrap = await tasks._sync_coin_backfill_item(uow, coin)
    assert "patterns_bootstrap" not in no_bootstrap


@pytest.mark.asyncio
async def test_market_data_tasks_run_history_and_manual_jobs(monkeypatch) -> None:
    db = object()
    coin = SimpleNamespace(symbol="BTCUSD_EVT", history_backfill_completed_at=None)
    monkeypatch.setattr(tasks, "AsyncUnitOfWork", lambda: _AsyncDbContext(db))

    monkeypatch.setattr(tasks, "async_redis_task_lock", lambda *args, **kwargs: _async_lock(False))
    skipped_backfill = await tasks._run_history_backfill()
    skipped_latest = await tasks._run_latest_history_sync()
    assert skipped_backfill["reason"] == "history_backfill_in_progress"
    assert skipped_latest["reason"] == "history_refresh_in_progress"

    monkeypatch.setattr(tasks, "async_redis_task_lock", lambda *args, **kwargs: _async_lock(True))

    async def fake_list_pending(self, *, symbol=None):
        del symbol
        return ["BTCUSD_EVT", "MISSING_EVT"]

    async def fake_list_ready(self):
        return ["BTCUSD_EVT", "MISSING_EVT"]

    async def fake_get_coin(self, symbol: str, include_deleted: bool = False):
        del include_deleted
        return coin if symbol.strip().upper() == "BTCUSD_EVT" else None

    monkeypatch.setattr(tasks.MarketDataQueryService, "list_coin_symbols_pending_backfill", fake_list_pending)
    monkeypatch.setattr(tasks.MarketDataQueryService, "list_coin_symbols_ready_for_latest_sync", fake_list_ready)
    monkeypatch.setattr(tasks.MarketDataQueryService, "get_coin_read_by_symbol", fake_get_coin)
    monkeypatch.setattr(
        tasks,
        "_sync_coin_backfill_item",
        lambda uow, coin, force=False: __import__("asyncio").sleep(0, result={"symbol": coin.symbol, "created": 5, "status": "ok"}),
    )
    monkeypatch.setattr(
        tasks,
        "_sync_coin_latest_item",
        lambda uow, coin, force=False: __import__("asyncio").sleep(0, result={"symbol": coin.symbol, "created": 2, "status": "ok"}),
    )

    backfill = await tasks._run_history_backfill()
    latest = await tasks._run_latest_history_sync()

    assert backfill["history_points_created"] == 5
    assert latest["history_points_created"] == 2

    invalid = await tasks._run_manual_coin_history_job(symbol="btcusd_evt", mode="bad")
    assert invalid["status"] == "error"

    async def missing_coin(self, symbol: str, include_deleted: bool = False):
        del symbol, include_deleted
        return

    monkeypatch.setattr(tasks.MarketDataQueryService, "get_coin_read_by_symbol", missing_coin)
    missing = await tasks._run_manual_coin_history_job(symbol="btcusd_evt", mode="backfill")
    assert missing["reason"] == "coin_not_found"

    monkeypatch.setattr(tasks.MarketDataQueryService, "get_coin_read_by_symbol", fake_get_coin)
    monkeypatch.setattr(
        tasks,
        "_sync_coin_backfill_item",
        lambda uow, coin, force=False: __import__("asyncio").sleep(0, result={"symbol": coin.symbol, "created": 6, "status": "ok"}),
    )
    monkeypatch.setattr(
        tasks,
        "_sync_coin_latest_item",
        lambda uow, coin, force=False: __import__("asyncio").sleep(0, result={"symbol": coin.symbol, "created": 3, "status": "ok"}),
    )

    assert (await tasks._run_manual_coin_history_job(symbol="btcusd_evt", mode="backfill", force=False))["mode"] == "backfill"
    assert (await tasks._run_manual_coin_history_job(symbol="btcusd_evt", mode="latest"))["mode"] == "latest"
    assert (await tasks._run_manual_coin_history_job(symbol="btcusd_evt", mode="auto"))["mode"] == "backfill"

    coin.history_backfill_completed_at = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
    assert (await tasks._run_manual_coin_history_job(symbol="btcusd_evt", mode="auto"))["mode"] == "latest"

    monkeypatch.setattr(tasks, "_run_history_backfill", lambda symbol=None: __import__("asyncio").sleep(0, result={"status": "ok", "mode": "backfill"}))
    monkeypatch.setattr(tasks, "_run_latest_history_sync", lambda: __import__("asyncio").sleep(0, result={"status": "ok", "mode": "latest"}))
    monkeypatch.setattr(
        tasks,
        "_run_manual_coin_history_job",
        lambda **kwargs: __import__("asyncio").sleep(0, result={"status": "ok", "mode": kwargs["mode"], "symbol": kwargs["symbol"]}),
    )

    assert (await tasks.bootstrap_observed_coins_history())["mode"] == "backfill"
    assert (await tasks.backfill_observed_coins_history(symbol="BTCUSD_EVT"))["mode"] == "backfill"
    assert (await tasks.refresh_observed_coins_history())["mode"] == "latest"
    assert (await tasks.run_coin_history_job(symbol="BTCUSD_EVT", mode="latest"))["symbol"] == "BTCUSD_EVT"
