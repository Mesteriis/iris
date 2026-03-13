from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
import src.apps.portfolio.selectors as portfolio_selectors_module
from sqlalchemy import select

import src.apps.portfolio.services as portfolio_services_module
from src.apps.portfolio.models import PortfolioAction, PortfolioBalance, PortfolioPosition, PortfolioState
from src.apps.portfolio.query_services import PortfolioQueryService
from src.apps.portfolio.services import PortfolioService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork
from tests.fusion_support import create_test_coin, upsert_coin_metrics
from tests.portfolio_support import create_exchange_account, create_market_decision


class _SingleBalancePlugin:
    async def fetch_balances(self):
        return [{"symbol": "NOCOMMITUSD_EVT", "balance": 1.0, "value_usd": 500.0}]

    async def fetch_positions(self):
        return []

    async def fetch_orders(self):
        return []

    async def fetch_trades(self):
        return []


def _seed_portfolio_projection_state(db_session):
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)
    decision = create_market_decision(
        db_session,
        coin_id=int(coin.id),
        timeframe=15,
        decision="BUY",
        confidence=0.8,
    )
    db_session.merge(
        PortfolioState(
            id=1,
            total_capital=100_000.0,
            allocated_capital=250.0,
            available_capital=99_750.0,
        )
    )
    db_session.add(
        PortfolioPosition(
            coin_id=int(coin.id),
            exchange_account_id=None,
            source_exchange="fixture",
            position_type="long",
            timeframe=15,
            entry_price=100.0,
            position_size=2.5,
            position_value=250.0,
            stop_loss=95.0,
            take_profit=110.0,
            status="open",
        )
    )
    db_session.add(
        PortfolioAction(
            coin_id=int(coin.id),
            action="OPEN_POSITION",
            size=250.0,
            confidence=0.8,
            decision_id=int(decision.id),
        )
    )
    db_session.commit()
    return coin, decision


@pytest.mark.asyncio
async def test_portfolio_query_returns_immutable_read_models(async_db_session, db_session) -> None:
    _seed_portfolio_projection_state(db_session)
    rows = await PortfolioQueryService(async_db_session).list_positions(limit=10)

    assert rows
    item = rows[0]
    assert item.symbol == "BTCUSD_EVT"
    with pytest.raises(FrozenInstanceError):
        item.symbol = "changed"


@pytest.mark.asyncio
async def test_portfolio_service_defers_commit_to_uow(async_db_session, db_session, monkeypatch) -> None:
    create_exchange_account(db_session, exchange_name="binance", account_name="write-path")
    monkeypatch.setattr(portfolio_services_module, "create_exchange_plugin", lambda account: _SingleBalancePlugin())

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await PortfolioService(uow).sync_exchange_balances(emit_events=False)
        assert result.balances == 1
        visible_before_commit = db_session.scalar(
            select(PortfolioBalance).where(PortfolioBalance.symbol == "NOCOMMITUSD_EVT").limit(1)
        )
        assert visible_before_commit is None

    db_session.expire_all()
    visible_after_rollback = db_session.scalar(
        select(PortfolioBalance).where(PortfolioBalance.symbol == "NOCOMMITUSD_EVT").limit(1)
    )
    assert visible_after_rollback is None


@pytest.mark.asyncio
async def test_portfolio_action_service_defers_commit_to_uow(async_db_session, db_session) -> None:
    btc, _decision = _seed_portfolio_projection_state(db_session)
    baseline = db_session.scalar(
        select(PortfolioAction)
        .where(PortfolioAction.coin_id == int(btc.id))
        .order_by(PortfolioAction.id.desc())
        .limit(1)
    )
    baseline_id = int(baseline.id) if baseline is not None else None

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await PortfolioService(uow).evaluate_portfolio_action(
            coin_id=int(btc.id),
            timeframe=15,
            emit_events=False,
        )
        assert result.status == "ok"
        visible_before_commit = db_session.scalar(
            select(PortfolioAction)
            .where(PortfolioAction.coin_id == int(btc.id))
            .order_by(PortfolioAction.id.desc())
            .limit(1)
        )
        assert (int(visible_before_commit.id) if visible_before_commit is not None else None) == baseline_id

    db_session.expire_all()
    visible_after_rollback = db_session.scalar(
        select(PortfolioAction)
        .where(PortfolioAction.coin_id == int(btc.id))
        .order_by(PortfolioAction.id.desc())
        .limit(1)
    )
    assert (int(visible_after_rollback.id) if visible_after_rollback is not None else None) == baseline_id


@pytest.mark.asyncio
async def test_portfolio_persistence_logs_cover_query_service_service_and_uow(
    async_db_session,
    db_session,
    monkeypatch,
) -> None:
    btc, _decision = _seed_portfolio_projection_state(db_session)
    events: list[str] = []

    def _debug(message: str, *args, **kwargs) -> None:
        del args, kwargs
        events.append(message)

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    create_exchange_account(db_session, exchange_name="binance", account_name="log-path")
    monkeypatch.setattr(portfolio_services_module, "create_exchange_plugin", lambda account: _SingleBalancePlugin())
    monkeypatch.setattr(PERSISTENCE_LOGGER, "debug", _debug)
    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)

    async with SessionUnitOfWork(async_db_session) as uow:
        await PortfolioQueryService(uow.session).list_positions(limit=5)
        await PortfolioService(uow).sync_exchange_balances(emit_events=False)
        await PortfolioService(uow).evaluate_portfolio_action(
            coin_id=int(btc.id),
            timeframe=15,
            emit_events=False,
        )

    assert "uow.begin" in events
    assert "query.list_portfolio_positions" in events
    assert "service.sync_exchange_balances" in events
    assert "service.evaluate_portfolio_action" in events
    assert "uow.rollback_uncommitted" in events


def test_portfolio_services_exports_no_public_async_query_wrappers() -> None:
    forbidden_exports = (
        "get_portfolio_state_async",
        "list_portfolio_actions_async",
        "list_portfolio_positions_async",
        "sync_exchange_balances_async",
        "_ensure_coin_for_balance_async",
        "_ensure_portfolio_state_async",
        "_refresh_portfolio_state_async",
        "_sync_balance_position_async",
        "_sync_balance_row_async",
    )

    for export_name in forbidden_exports:
        assert not hasattr(portfolio_services_module, export_name), export_name


def test_portfolio_modules_export_no_public_sync_selectors() -> None:
    forbidden_exports = (
        "PortfolioCompatibilityQuery",
        "get_portfolio_state",
        "list_portfolio_actions",
        "list_portfolio_positions",
    )

    for export_name in forbidden_exports:
        assert not hasattr(portfolio_selectors_module, export_name), export_name
