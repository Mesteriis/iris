from __future__ import annotations

from sqlalchemy import select

from app.models.coin import Coin
from app.portfolio.engine import sync_exchange_balances
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


def test_auto_watch_enables_coin_from_portfolio_balance(db_session) -> None:
    from app.exchanges.registry import register_exchange

    register_exchange("fixture_watch", AutoWatchPlugin)
    create_exchange_account(db_session, exchange_name="fixture_watch")

    result = sync_exchange_balances(db_session, emit_events=False)

    assert result["status"] == "ok"
    coin = db_session.scalar(select(Coin).where(Coin.symbol == "SOLUSD_EVT").limit(1))
    assert coin is not None
    assert coin.enabled is True
    assert coin.auto_watch_enabled is True
    assert coin.auto_watch_source == "portfolio"
    assert coin.next_history_sync_at is not None
