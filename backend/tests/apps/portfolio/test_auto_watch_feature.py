import pytest
from iris.apps.market_data.models import Coin
from iris.apps.portfolio.services import PortfolioService, PortfolioSideEffectDispatcher
from iris.core.db.uow import SessionUnitOfWork
from sqlalchemy import select

from tests.portfolio_support import create_exchange_account


class AutoWatchPlugin:
    def __init__(self, account) -> None:
        self.account = account

    async def fetch_balances(self):
        return [{"symbol": "SOLUSD_EVT", "balance": 12.0, "value_usd": 420.0}]

    async def fetch_positions(self):
        return []

    async def fetch_orders(self):
        return []

    async def fetch_trades(self):
        return []


@pytest.mark.asyncio
async def test_auto_watch_enables_coin_from_portfolio_balance(async_db_session, db_session) -> None:
    from iris.apps.portfolio.clients import register_exchange

    register_exchange("fixture_watch", AutoWatchPlugin)
    create_exchange_account(db_session, exchange_name="fixture_watch")

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await PortfolioService(uow).sync_exchange_balances(emit_events=False)
        await uow.commit()
        await PortfolioSideEffectDispatcher().apply_sync_result(result)

    db_session.expire_all()

    assert result.status == "ok"
    coin = db_session.scalar(select(Coin).where(Coin.symbol == "SOLUSD_EVT").limit(1))
    assert coin is not None
    assert coin.enabled is True
    assert coin.auto_watch_enabled is True
    assert coin.auto_watch_source == "portfolio"
    assert coin.next_history_sync_at is not None
