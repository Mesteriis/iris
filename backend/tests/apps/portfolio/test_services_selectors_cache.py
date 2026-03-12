from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.apps.market_data.models import Coin
from app.apps.indicators.models import CoinMetrics
from app.apps.portfolio import cache, tasks
from app.apps.portfolio.cache import (
    PORTFOLIO_BALANCES_CACHE_KEY,
    PORTFOLIO_STATE_CACHE_KEY,
    cache_portfolio_balances,
    cache_portfolio_balances_async,
    cache_portfolio_state,
    cache_portfolio_state_async,
    read_cached_portfolio_balances,
    read_cached_portfolio_balances_async,
    read_cached_portfolio_state,
    read_cached_portfolio_state_async,
)
from app.apps.portfolio.models import ExchangeAccount, PortfolioBalance, PortfolioPosition, PortfolioState
from app.apps.portfolio.selectors import get_portfolio_state, list_portfolio_actions, list_portfolio_positions
from app.apps.portfolio.services import (
    _apply_auto_watch,
    _ensure_coin_for_balance_async,
    _ensure_portfolio_state_async,
    _refresh_portfolio_state_async,
    _sync_balance_position_async,
    _sync_balance_row_async,
    get_portfolio_state_async,
    list_portfolio_actions_async,
    list_portfolio_positions_async,
    sync_exchange_balances_async,
)
from tests.portfolio_support import create_exchange_account


class _SyncCacheClient:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    def set(self, key: str, value: str, *, ex: int) -> None:
        self.storage[key] = value

    def get(self, key: str) -> str | None:
        return self.storage.get(key)


class _AsyncCacheClient:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.storage[key] = value

    async def get(self, key: str) -> str | None:
        return self.storage.get(key)


class _FixturePlugin:
    def __init__(self, account) -> None:
        self.account = account

    async def fetch_balances(self):
        return [
            {"symbol": "BTCUSD_EVT", "balance": 1.5, "value_usd": 750.0},
            {"symbol": "NEWUSD_EVT", "balance": 4.0, "value_usd": 520.0},
            {"symbol": "", "balance": 1.0, "value_usd": 10.0},
        ]

    async def fetch_positions(self):
        return []

    async def fetch_orders(self):
        return []

    async def fetch_trades(self):
        return []


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


def test_portfolio_cache_and_selectors_cover_cached_and_uncached_paths(db_session, seeded_api_state, monkeypatch, settings) -> None:
    sync_client = _SyncCacheClient()
    async_client = _AsyncCacheClient()

    cache.get_portfolio_cache_client.cache_clear()
    cache.get_async_portfolio_cache_client.cache_clear()
    monkeypatch.setattr(cache.Redis, "from_url", staticmethod(lambda url, decode_responses: (url, decode_responses)))
    monkeypatch.setattr(cache.AsyncRedis, "from_url", staticmethod(lambda url, decode_responses: (url, decode_responses)))
    assert cache.get_portfolio_cache_client() == (settings.redis_url, True)
    assert cache.get_async_portfolio_cache_client() == (settings.redis_url, True)
    cache.get_portfolio_cache_client.cache_clear()
    cache.get_async_portfolio_cache_client.cache_clear()

    monkeypatch.setattr(cache, "get_portfolio_cache_client", lambda: sync_client)
    monkeypatch.setattr(cache, "get_async_portfolio_cache_client", lambda: async_client)

    payload = {"total_capital": 1000.0, "allocated_capital": 100.0}
    balances = [{"symbol": "BTCUSD_EVT", "value_usd": 750.0}]
    cache_portfolio_state(payload)
    cache_portfolio_balances(balances)
    assert sync_client.storage[PORTFOLIO_STATE_CACHE_KEY]
    assert read_cached_portfolio_state() == payload
    assert read_cached_portfolio_balances() == balances
    sync_client.storage.clear()
    assert read_cached_portfolio_state() is None
    assert read_cached_portfolio_balances() is None
    cache_portfolio_state(payload)
    cache_portfolio_balances(balances)
    assert cache._parse_portfolio_state("{") is None
    assert cache._parse_portfolio_balances("{") is None

    async def _async_checks() -> None:
        await cache_portfolio_state_async(payload)
        await cache_portfolio_balances_async(balances)
        assert await read_cached_portfolio_state_async() == payload
        assert await read_cached_portfolio_balances_async() == balances
        async_client.storage.clear()
        assert await read_cached_portfolio_state_async() is None
        assert await read_cached_portfolio_balances_async() is None

    import asyncio

    asyncio.run(_async_checks())

    positions = list_portfolio_positions(db_session, limit=5)
    assert positions[0]["symbol"] == "BTCUSD_EVT"
    assert positions[0]["latest_decision"] == "BUY"
    assert positions[0]["risk_to_stop"] is not None

    actions = list_portfolio_actions(db_session, limit=5)
    assert actions[0]["action"] == "OPEN_POSITION"
    assert actions[0]["market_decision"] == "BUY"

    monkeypatch.setattr("app.apps.portfolio.selectors.read_cached_portfolio_state", lambda: {"cached": True})
    assert get_portfolio_state(db_session) == {"cached": True}

    monkeypatch.setattr("app.apps.portfolio.selectors.read_cached_portfolio_state", lambda: None)
    state = get_portfolio_state(db_session)
    assert state["open_positions"] == 1
    assert state["max_positions"] == settings.portfolio_max_positions

    db_session.execute(delete(PortfolioState))
    db_session.execute(delete(PortfolioPosition))
    db_session.commit()
    empty_state = get_portfolio_state(db_session)
    assert empty_state["total_capital"] == 0.0
    assert empty_state["open_positions"] == 0


@pytest.mark.asyncio
async def test_portfolio_async_services_cover_balance_sync_and_task_wrapper(async_db_session, db_session, seeded_api_state, monkeypatch) -> None:
    btc = seeded_api_state["btc"]
    account = db_session.scalar(select(ExchangeAccount).limit(1))
    assert account is not None

    positions = await list_portfolio_positions_async(async_db_session, limit=5)
    assert positions[0]["symbol"] == "BTCUSD_EVT"
    assert positions[0]["regime"] == "bull_trend"

    actions = await list_portfolio_actions_async(async_db_session, limit=5)
    assert actions[0]["action"] == "OPEN_POSITION"

    monkeypatch.setattr("app.apps.portfolio.services.read_cached_portfolio_state_async", lambda: __import__("asyncio").sleep(0, result={"cached": True}))
    assert await get_portfolio_state_async(async_db_session) == {"cached": True}

    cached_states: list[dict[str, object]] = []
    monkeypatch.setattr("app.apps.portfolio.services.read_cached_portfolio_state_async", lambda: __import__("asyncio").sleep(0, result=None))
    monkeypatch.setattr("app.apps.portfolio.services.cache_portfolio_state_async", lambda payload: __import__("asyncio").sleep(0, result=cached_states.append(payload)))
    state = await get_portfolio_state_async(async_db_session)
    assert state["open_positions"] == 1
    assert cached_states

    await async_db_session.execute(delete(PortfolioState))
    await async_db_session.execute(delete(PortfolioPosition))
    await async_db_session.commit()
    missing_state = await get_portfolio_state_async(async_db_session)
    assert missing_state["total_capital"] == 0.0

    ensured_state = await _ensure_portfolio_state_async(async_db_session)
    assert ensured_state.id == 1

    existing_coin = await _ensure_coin_for_balance_async(async_db_session, symbol="BTCUSD_EVT", exchange_name="fixture")
    assert existing_coin.id == btc.id
    new_coin = await _ensure_coin_for_balance_async(async_db_session, symbol="NEWUSD_EVT", exchange_name="fixture")
    assert new_coin.symbol == "NEWUSD_EVT"
    assert new_coin.enabled is False

    metrics = await async_db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(btc.id)))
    assert metrics is not None
    metrics.price_current = 500.0
    metrics.atr_14 = 15.0
    await async_db_session.commit()

    await _sync_balance_position_async(
        async_db_session,
        account=account,
        coin=existing_coin,
        value_usd=900.0,
        balance=1.8,
    )
    await async_db_session.commit()
    position = await async_db_session.scalar(
        select(PortfolioPosition)
        .where(PortfolioPosition.exchange_account_id == int(account.id), PortfolioPosition.coin_id == int(existing_coin.id))
        .limit(1)
    )
    assert position is not None
    assert float(position.position_value) == 900.0

    await _sync_balance_position_async(
        async_db_session,
        account=account,
        coin=existing_coin,
        value_usd=0.0,
        balance=0.0,
    )
    await async_db_session.commit()
    closed_position = await async_db_session.scalar(
        select(PortfolioPosition)
        .where(PortfolioPosition.exchange_account_id == int(account.id), PortfolioPosition.coin_id == int(existing_coin.id))
        .order_by(PortfolioPosition.id.desc())
        .limit(1)
    )
    assert closed_position is not None
    assert closed_position.status == "closed"

    zero_coin = await _ensure_coin_for_balance_async(async_db_session, symbol="ZEROUSD_EVT", exchange_name="fixture")
    await _sync_balance_position_async(
        async_db_session,
        account=account,
        coin=zero_coin,
        value_usd=0.0,
        balance=0.0,
    )
    await async_db_session.commit()
    assert await async_db_session.scalar(
        select(PortfolioPosition)
        .where(PortfolioPosition.exchange_account_id == int(account.id), PortfolioPosition.coin_id == int(zero_coin.id))
        .limit(1)
    ) is None

    assert not _apply_auto_watch(coin=btc, value_usd=10.0)
    btc.enabled = False
    btc.auto_watch_enabled = False
    changed = _apply_auto_watch(coin=btc, value_usd=1000.0)
    assert changed
    assert btc.enabled is True

    published_events: list[str] = []
    monkeypatch.setattr("app.apps.portfolio.services.publish_event", lambda event_type, payload: published_events.append(event_type))
    none_row = await _sync_balance_row_async(
        async_db_session,
        account_id=999999,
        exchange_name="fixture",
        balance_row={"symbol": "BTCUSD_EVT", "balance": 1.0, "value_usd": 500.0},
        emit_events=True,
    )
    assert none_row == (None, None)
    blank_row = await _sync_balance_row_async(
        async_db_session,
        account_id=int(account.id),
        exchange_name="fixture",
        balance_row={"symbol": "", "balance": 1.0, "value_usd": 500.0},
        emit_events=True,
    )
    assert blank_row == (None, None)

    cached_row, payload = await _sync_balance_row_async(
        async_db_session,
        account_id=int(account.id),
        exchange_name="fixture",
        balance_row={"symbol": "AUTOUSD_EVT", "balance": 2.0, "value_usd": 650.0},
        emit_events=True,
    )
    assert cached_row is not None and payload is not None
    assert cached_row["auto_watch_enabled"] is True
    assert payload["timeframe"] == 1440
    assert "coin_auto_watch_enabled" in published_events

    updated_cached_row, quiet_payload = await _sync_balance_row_async(
        async_db_session,
        account_id=int(account.id),
        exchange_name="fixture",
        balance_row={"symbol": "AUTOUSD_EVT", "balance": 3.0, "value_usd": 900.0},
        emit_events=False,
    )
    assert updated_cached_row is not None
    assert quiet_payload == {
        "exchange_account_id": int(account.id),
        "symbol": "AUTOUSD_EVT",
        "balance": 3.0,
        "value_usd": 900.0,
    }

    cached_state_payloads: list[dict[str, object]] = []
    monkeypatch.setattr("app.apps.portfolio.services.cache_portfolio_state_async", lambda payload: __import__("asyncio").sleep(0, result=cached_state_payloads.append(payload)))
    await _refresh_portfolio_state_async(async_db_session)
    assert cached_state_payloads

    cached_balance_payloads: list[list[dict[str, object]]] = []
    monkeypatch.setattr("app.apps.portfolio.services.create_exchange_plugin", lambda account: _FixturePlugin(account))
    monkeypatch.setattr("app.apps.portfolio.services.cache_portfolio_balances_async", lambda payload: __import__("asyncio").sleep(0, result=cached_balance_payloads.append(payload)))
    published_events.clear()
    sync_result = await sync_exchange_balances_async(async_db_session, emit_events=True)
    assert sync_result["status"] == "ok"
    assert sync_result["accounts"] >= 1
    assert sync_result["balances"] >= 2
    assert cached_balance_payloads
    assert "portfolio_balance_updated" in published_events
    assert "portfolio_position_changed" in published_events

    quiet_sync_result = await sync_exchange_balances_async(async_db_session, emit_events=False)
    assert quiet_sync_result["status"] == "ok"
    assert quiet_sync_result["items"]

    fake_db = object()
    monkeypatch.setattr(tasks, "AsyncSessionLocal", lambda: _AsyncDbContext(fake_db))
    monkeypatch.setattr(tasks, "async_redis_task_lock", lambda *args, **kwargs: _async_lock(False))
    assert (await tasks.portfolio_sync_job())["reason"] == "portfolio_sync_in_progress"
    monkeypatch.setattr(tasks, "async_redis_task_lock", lambda *args, **kwargs: _async_lock(True))
    monkeypatch.setattr(tasks, "sync_exchange_balances_async", lambda db, emit_events=True: __import__("asyncio").sleep(0, result={"status": "ok", "db": db is fake_db, "emit": emit_events}))
    assert await tasks.portfolio_sync_job() == {"status": "ok", "db": True, "emit": True}
