from __future__ import annotations

import json

from redis import Redis
from sqlalchemy import select

from src.apps.market_data.models import Coin
from src.apps.portfolio.models import PortfolioBalance
from src.apps.portfolio.models import PortfolioPosition
from src.apps.portfolio.engine import sync_exchange_balances
from src.apps.portfolio.cache import read_cached_portfolio_balances
from tests.fusion_support import create_test_coin, upsert_coin_metrics
from tests.portfolio_support import create_exchange_account


class FixtureBalancePlugin:
    def __init__(self, account) -> None:
        self.account = account

    async def fetch_balances(self):
        return [
            {"symbol": "BTCUSD_EVT", "balance": 2.0, "value_usd": 500.0},
            {"symbol": "ETHUSD_EVT", "balance": 3.0, "value_usd": 240.0},
        ]

    async def fetch_positions(self):
        return []

    async def fetch_orders(self):
        return []

    async def fetch_trades(self):
        return []


def test_portfolio_sync_updates_balances_and_emits_events(db_session, redis_client, settings) -> None:
    from src.apps.portfolio.clients import register_exchange

    register_exchange("fixture_sync", FixtureBalancePlugin)
    create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    create_test_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test")
    for coin in db_session.scalars(select(Coin).where(Coin.symbol.in_(("BTCUSD_EVT", "ETHUSD_EVT")))).all():
        upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=1440)
    account = create_exchange_account(db_session, exchange_name="fixture_sync")

    result = sync_exchange_balances(db_session, emit_events=True)

    assert result["status"] == "ok"
    assert int(result["accounts"]) == 1
    assert int(result["balances"]) == 2
    assert db_session.scalar(select(PortfolioBalance).where(PortfolioBalance.exchange_account_id == account.id).limit(1)) is not None
    assert db_session.scalar(select(PortfolioPosition).where(PortfolioPosition.exchange_account_id == account.id).limit(1)) is not None
    cached = read_cached_portfolio_balances()
    assert cached is not None
    assert len(cached) == 2

    from src.runtime.streams.publisher import flush_publisher

    assert flush_publisher(timeout=5.0)
    messages = redis_client.xrange(settings.event_stream_name, "-", "+")
    event_types = [fields["event_type"] for _, fields in messages]
    assert "portfolio_balance_updated" in event_types
    assert "portfolio_position_changed" in event_types
