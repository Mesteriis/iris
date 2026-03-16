from contextlib import asynccontextmanager

import pytest
from sqlalchemy import delete, select
from src.apps.indicators.models import CoinMetrics
from src.apps.portfolio import cache, tasks
from src.apps.portfolio.cache import (
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
from src.apps.portfolio.models import ExchangeAccount, PortfolioPosition, PortfolioState
from src.apps.portfolio.query_services import PortfolioQueryService
from src.apps.portfolio.read_models import PortfolioStateReadModel
from src.apps.portfolio.results import PortfolioSyncItem, PortfolioSyncResult
from src.apps.portfolio.serializers import portfolio_sync_result_payload
from src.apps.portfolio.services import PortfolioService, PortfolioSideEffectDispatcher
from src.core.db.uow import SessionUnitOfWork


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


@asynccontextmanager
async def _async_lock(acquired: bool):
    yield acquired


@pytest.mark.asyncio
async def test_portfolio_cache_and_query_service_cover_cached_and_uncached_paths(
    async_db_session,
    db_session,
    seeded_api_state,
    monkeypatch,
    settings,
) -> None:
    del seeded_api_state
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

    await cache_portfolio_state_async(payload)
    await cache_portfolio_balances_async(balances)
    assert await read_cached_portfolio_state_async() == payload
    assert await read_cached_portfolio_balances_async() == balances
    async_client.storage.clear()
    assert await read_cached_portfolio_state_async() is None
    assert await read_cached_portfolio_balances_async() is None

    query_service = PortfolioQueryService(async_db_session)
    positions = await query_service.list_positions(limit=5)
    assert positions[0].symbol == "BTCUSD_EVT"
    assert positions[0].latest_decision == "BUY"
    assert positions[0].risk_to_stop is not None

    actions = await query_service.list_actions(limit=5)
    assert actions[0].action == "OPEN_POSITION"
    assert actions[0].market_decision == "BUY"

    monkeypatch.setattr(
        "src.apps.portfolio.query_services.read_cached_portfolio_state_async",
        lambda: __import__("asyncio").sleep(
            0,
            result={
                "total_capital": 1.0,
                "allocated_capital": 0.2,
                "available_capital": 0.8,
                "updated_at": "2026-03-12T10:00:00+00:00",
                "open_positions": 4,
                "max_positions": 7,
            },
        ),
    )
    cached_state = await PortfolioQueryService(async_db_session).get_state()
    assert cached_state.total_capital == 1.0
    assert cached_state.max_positions == 7

    monkeypatch.setattr(
        "src.apps.portfolio.query_services.read_cached_portfolio_state_async",
        lambda: __import__("asyncio").sleep(0, result=None),
    )
    state = await PortfolioQueryService(async_db_session).get_state()
    assert state.open_positions == 1
    assert state.max_positions == settings.portfolio_max_positions

    await async_db_session.execute(delete(PortfolioState))
    await async_db_session.execute(delete(PortfolioPosition))
    await async_db_session.commit()
    empty_state = await PortfolioQueryService(async_db_session).get_state()
    assert empty_state.total_capital == 0.0
    assert empty_state.open_positions == 0


@pytest.mark.asyncio
async def test_portfolio_async_query_service_service_and_task_wrapper(
    async_db_session,
    db_session,
    seeded_api_state,
    monkeypatch,
) -> None:
    btc = seeded_api_state["btc"]
    account = db_session.scalar(select(ExchangeAccount).limit(1))
    assert account is not None

    positions = await PortfolioQueryService(async_db_session).list_positions(limit=5)
    assert positions[0].symbol == "BTCUSD_EVT"
    assert positions[0].regime == "bull_trend"

    actions = await PortfolioQueryService(async_db_session).list_actions(limit=5)
    assert actions[0].action == "OPEN_POSITION"

    monkeypatch.setattr(
        "src.apps.portfolio.query_services.read_cached_portfolio_state_async",
        lambda: __import__("asyncio").sleep(
            0,
            result={
                "total_capital": 1.0,
                "allocated_capital": 0.2,
                "available_capital": 0.8,
                "updated_at": "2026-03-12T10:00:00+00:00",
                "open_positions": 4,
                "max_positions": 7,
            },
        ),
    )
    cached_state = await PortfolioQueryService(async_db_session).get_state()
    assert cached_state.total_capital == 1.0
    assert cached_state.open_positions == 4

    cached_state_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(
        "src.apps.portfolio.query_services.read_cached_portfolio_state_async",
        lambda: __import__("asyncio").sleep(0, result=None),
    )
    monkeypatch.setattr(
        "src.apps.portfolio.query_services.cache_portfolio_state_async",
        lambda payload: __import__("asyncio").sleep(0, result=cached_state_payloads.append(payload)),
    )
    state = await PortfolioQueryService(async_db_session).get_state()
    assert state.open_positions == 1
    assert cached_state_payloads[-1]["max_positions"] == state.max_positions

    await async_db_session.execute(delete(PortfolioState))
    await async_db_session.execute(delete(PortfolioPosition))
    await async_db_session.commit()
    missing_state = await PortfolioQueryService(async_db_session).get_state()
    assert missing_state.total_capital == 0.0
    assert missing_state.open_positions == 0

    async with SessionUnitOfWork(async_db_session) as uow:
        service = PortfolioService(uow)
        ensured_state = await service._ensure_portfolio_state()
        assert ensured_state.id == 1

        existing_coin = await service._ensure_coin_for_balance(symbol="BTCUSD_EVT", exchange_name="fixture")
        assert existing_coin.id == btc.id
        new_coin = await service._ensure_coin_for_balance(symbol="NEWUSD_EVT", exchange_name="fixture")
        assert new_coin.symbol == "NEWUSD_EVT"
        assert new_coin.enabled is False

        metrics = await async_db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(btc.id)))
        assert metrics is not None
        metrics.price_current = 500.0
        metrics.atr_14 = 15.0
        await uow.flush()

        await service._sync_balance_position(
            account=account,
            coin=existing_coin,
            value_usd=900.0,
            balance=1.8,
        )
        position = await async_db_session.scalar(
            select(PortfolioPosition)
            .where(PortfolioPosition.exchange_account_id == int(account.id), PortfolioPosition.coin_id == int(existing_coin.id))
            .limit(1)
        )
        assert position is not None
        assert float(position.position_value) == 900.0

        await service._sync_balance_position(
            account=account,
            coin=existing_coin,
            value_usd=0.0,
            balance=0.0,
        )
        closed_position = await async_db_session.scalar(
            select(PortfolioPosition)
            .where(PortfolioPosition.exchange_account_id == int(account.id), PortfolioPosition.coin_id == int(existing_coin.id))
            .order_by(PortfolioPosition.id.desc())
            .limit(1)
        )
        assert closed_position is not None
        assert closed_position.status == "closed"

        zero_coin = await service._ensure_coin_for_balance(symbol="ZEROUSD_EVT", exchange_name="fixture")
        await service._sync_balance_position(
            account=account,
            coin=zero_coin,
            value_usd=0.0,
            balance=0.0,
        )
        assert await async_db_session.scalar(
            select(PortfolioPosition)
            .where(PortfolioPosition.exchange_account_id == int(account.id), PortfolioPosition.coin_id == int(zero_coin.id))
            .limit(1)
        ) is None

        assert not service._apply_auto_watch(coin=existing_coin, value_usd=10.0)
        existing_coin.enabled = False
        existing_coin.auto_watch_enabled = False
        changed = service._apply_auto_watch(coin=existing_coin, value_usd=1000.0)
        assert changed
        assert existing_coin.enabled is True

        blank_row = await service._sync_balance_row(
            account=account,
            balance_row={"symbol": "", "balance": 1.0, "value_usd": 500.0},
            emit_events=True,
        )
        assert blank_row is None

        outcome = await service._sync_balance_row(
            account=account,
            balance_row={"symbol": "AUTOUSD_EVT", "balance": 2.0, "value_usd": 650.0},
            emit_events=True,
        )
        assert outcome is not None
        assert outcome.cached_row.auto_watch_enabled is True
        assert {event.event_type for event in outcome.pending_events} == {
            "coin_auto_watch_enabled",
            "portfolio_balance_updated",
            "portfolio_position_changed",
        }

        quiet_outcome = await service._sync_balance_row(
            account=account,
            balance_row={"symbol": "AUTOUSD_EVT", "balance": 3.0, "value_usd": 900.0},
            emit_events=False,
        )
        assert quiet_outcome is not None
        assert quiet_outcome.item.symbol == "AUTOUSD_EVT"
        assert quiet_outcome.item.value_usd == 900.0
        assert quiet_outcome.pending_events == ()

        refreshed_state = await service._refresh_portfolio_state()
        assert refreshed_state.total_capital > 0
        assert refreshed_state.updated_at is not None

    cached_balance_payloads: list[list[dict[str, object]]] = []
    cached_sync_state_payloads: list[dict[str, object]] = []
    published_events: list[str] = []
    monkeypatch.setattr("src.apps.portfolio.services.create_exchange_plugin", lambda item: _FixturePlugin(item))
    monkeypatch.setattr(
        "src.apps.portfolio.services.cache_portfolio_balances_async",
        lambda payload: __import__("asyncio").sleep(0, result=cached_balance_payloads.append(payload)),
    )
    monkeypatch.setattr(
        "src.apps.portfolio.services.cache_portfolio_state_async",
        lambda payload: __import__("asyncio").sleep(0, result=cached_sync_state_payloads.append(payload)),
    )
    monkeypatch.setattr(
        "src.apps.portfolio.services.publish_event",
        lambda event_type, payload: published_events.append(event_type),
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        sync_result = await PortfolioService(uow).sync_exchange_balances(emit_events=True)
        assert sync_result.status == "ok"
        assert sync_result.accounts >= 1
        assert sync_result.balances >= 2
        assert sync_result.cached_rows
        assert "portfolio_balance_updated" in {event.event_type for event in sync_result.pending_events}
        await uow.commit()

    await PortfolioSideEffectDispatcher().apply_sync_result(sync_result)
    assert cached_balance_payloads
    assert cached_sync_state_payloads
    assert "portfolio_balance_updated" in published_events
    assert "portfolio_position_changed" in published_events

    async with SessionUnitOfWork(async_db_session) as uow:
        quiet_sync_result = await PortfolioService(uow).sync_exchange_balances(emit_events=False)
        assert quiet_sync_result.status == "ok"
        assert quiet_sync_result.items
        assert all(
            event.event_type not in {"portfolio_balance_updated", "portfolio_position_changed"}
            for event in quiet_sync_result.pending_events
        )

    events: list[str] = []

    @asynccontextmanager
    async def _lock(acquired: bool):
        events.append(f"lock:{acquired}")
        yield acquired

    monkeypatch.setattr(tasks, "async_redis_task_lock", lambda *args, **kwargs: _lock(False))
    skipped = await tasks.portfolio_sync_job()
    assert skipped == {"status": "skipped", "reason": "portfolio_sync_in_progress"}

    result = PortfolioSyncResult(
        status="ok",
        accounts=1,
        items=(
            PortfolioSyncItem(exchange_account_id=1, symbol="BTCUSD_EVT", balance=1.0, value_usd=100.0),
            PortfolioSyncItem(exchange_account_id=1, symbol="ETHUSD_EVT", balance=2.0, value_usd=200.0),
        ),
        cached_rows=(),
        state=PortfolioStateReadModel(
            total_capital=1000.0,
            allocated_capital=300.0,
            available_capital=700.0,
            updated_at="2026-03-14T00:00:00+00:00",
            open_positions=2,
            max_positions=8,
        ),
        pending_events=(),
    )

    class _UowContext:
        async def __aenter__(self):
            events.append("uow_enter")
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            events.append("uow_exit")
            return False

        @property
        def session(self):
            return "async-db"

        async def commit(self) -> None:
            events.append("uow_commit")

    class _PortfolioService:
        def __init__(self, uow) -> None:
            self._uow = uow

        async def sync_exchange_balances(self, *, emit_events: bool):
            events.append(f"sync:{self._uow.session}:{emit_events}")
            return result

    class _PortfolioSideEffectDispatcher:
        async def apply_sync_result(self, result) -> None:
            events.append(f"side_effects:{result.status}")

    monkeypatch.setattr(tasks, "async_redis_task_lock", lambda *args, **kwargs: _lock(True))
    monkeypatch.setattr(tasks, "AsyncUnitOfWork", lambda: _UowContext())
    monkeypatch.setattr(tasks, "PortfolioService", _PortfolioService)
    monkeypatch.setattr(tasks, "PortfolioSideEffectDispatcher", _PortfolioSideEffectDispatcher)
    executed = await tasks.portfolio_sync_job()
    assert executed == portfolio_sync_result_payload(result)
    assert events[1:6] == [
        "lock:True",
        "uow_enter",
        "sync:async-db:True",
        "uow_commit",
        "uow_exit",
    ]
    assert events[-1] == "side_effects:ok"
