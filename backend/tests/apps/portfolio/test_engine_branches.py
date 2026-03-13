from __future__ import annotations

from sqlalchemy import select

from src.apps.indicators.models import CoinMetrics
from src.apps.portfolio.engine import (
    _ensure_coin_for_balance,
    _maybe_auto_watch_coin,
    _rebalance_existing_position,
    _sync_balance_position,
    calculate_position_size,
    calculate_stops,
    ensure_portfolio_state,
    evaluate_portfolio_action,
    refresh_portfolio_state,
    sync_exchange_balances,
)
from src.apps.portfolio.models import ExchangeAccount, PortfolioAction, PortfolioBalance, PortfolioPosition
from tests.fusion_support import create_test_coin, upsert_coin_metrics
from tests.portfolio_support import create_exchange_account, create_market_decision, create_sector


def test_portfolio_state_helpers_and_skip_paths(db_session) -> None:
    state = ensure_portfolio_state(db_session)
    refreshed = refresh_portfolio_state(db_session)
    assert state.id == 1
    assert refreshed.available_capital == refreshed.total_capital

    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    assert evaluate_portfolio_action(db_session, coin_id=int(coin.id), timeframe=15, emit_events=False)["reason"] == "decision_not_found"
    create_market_decision(db_session, coin_id=int(coin.id), timeframe=15, decision="BUY", confidence=0.8)
    assert evaluate_portfolio_action(db_session, coin_id=int(coin.id), timeframe=15, emit_events=False)["reason"] == "coin_metrics_not_found"


def test_portfolio_engine_rebalances_existing_positions(db_session) -> None:
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    metrics = upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bear_trend", timeframe=15)
    create_market_decision(db_session, coin_id=int(coin.id), timeframe=15, decision="BUY", confidence=0.45)
    open_result = evaluate_portfolio_action(db_session, coin_id=int(coin.id), timeframe=15, emit_events=False)
    position = db_session.scalar(select(PortfolioPosition).where(PortfolioPosition.coin_id == int(coin.id), PortfolioPosition.timeframe == 15).limit(1))
    assert open_result["action"] == "OPEN_POSITION"
    assert position is not None

    metrics.market_regime = "bull_trend"
    db_session.commit()
    create_market_decision(db_session, coin_id=int(coin.id), timeframe=15, decision="BUY", confidence=0.95)
    increased = evaluate_portfolio_action(db_session, coin_id=int(coin.id), timeframe=15, emit_events=False)
    assert increased["action"] == "INCREASE_POSITION"

    create_market_decision(db_session, coin_id=int(coin.id), timeframe=15, decision="BUY", confidence=0.95)
    held = evaluate_portfolio_action(db_session, coin_id=int(coin.id), timeframe=15, emit_events=False)
    assert held["action"] in {"HOLD_POSITION", "INCREASE_POSITION"}

    create_market_decision(db_session, coin_id=int(coin.id), timeframe=15, decision="SELL", confidence=0.4)
    reduced = evaluate_portfolio_action(db_session, coin_id=int(coin.id), timeframe=15, emit_events=False)
    db_session.refresh(position)
    assert reduced["action"] == "REDUCE_POSITION"
    assert position.status == "partial"

    create_market_decision(db_session, coin_id=int(coin.id), timeframe=15, decision="SELL", confidence=0.8)
    closed = evaluate_portfolio_action(db_session, coin_id=int(coin.id), timeframe=15, emit_events=False)
    db_session.refresh(position)
    assert closed["action"] == "CLOSE_POSITION"
    assert position.status == "closed"


def test_portfolio_balance_helpers_cover_auto_watch_and_closing(db_session, monkeypatch) -> None:
    sector = create_sector(db_session, name="payments")
    account = create_exchange_account(db_session, exchange_name="fixture_close")
    coin = create_test_coin(db_session, symbol="XRPUSD_EVT", name="Ripple Event Test")
    coin.sector_id = int(sector.id)
    db_session.commit()
    upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=1440)

    existing = _ensure_coin_for_balance(db_session, symbol="XRPUSD_EVT", exchange_name="fixture_close")
    created = _ensure_coin_for_balance(db_session, symbol="SOLUSD_EVT", exchange_name="fixture_close")
    assert existing.id == coin.id
    assert created.symbol == "SOLUSD_EVT"
    assert created.sector_code == "portfolio"
    created_metrics = db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(created.id)).limit(1))
    assert created_metrics is not None

    published: list[str] = []
    monkeypatch.setattr("src.apps.portfolio.engine.publish_event", lambda event_type, payload: published.append(event_type))
    assert _maybe_auto_watch_coin(db_session, coin=coin, value_usd=1.0, exchange_name="fixture_close") is False
    assert _maybe_auto_watch_coin(db_session, coin=coin, value_usd=500.0, exchange_name="fixture_close") is True
    assert published[-1] == "coin_auto_watch_enabled"
    assert _maybe_auto_watch_coin(db_session, coin=coin, value_usd=500.0, exchange_name="fixture_close") is False

    _sync_balance_position(db_session, account=account, coin=coin, value_usd=250.0, balance=5.0)
    db_session.commit()
    position = db_session.scalar(
        select(PortfolioPosition)
        .where(PortfolioPosition.exchange_account_id == int(account.id), PortfolioPosition.coin_id == int(coin.id))
        .limit(1)
    )
    assert position is not None and position.status == "open"
    _sync_balance_position(db_session, account=account, coin=coin, value_usd=0.0, balance=0.0)
    db_session.commit()
    db_session.refresh(position)
    assert position.status == "closed"


def test_portfolio_sync_skips_blank_balances(db_session) -> None:
    class BlankPlugin:
        def __init__(self, account: ExchangeAccount) -> None:
            self.account = account

        async def fetch_balances(self):
            return [{"symbol": "", "balance": 1.0, "value_usd": 20.0}]

        async def fetch_positions(self):
            return []

        async def fetch_orders(self):
            return []

        async def fetch_trades(self):
            return []

    from src.apps.portfolio.clients import register_exchange

    register_exchange("fixture_blank", BlankPlugin)
    create_exchange_account(db_session, exchange_name="fixture_blank")
    result = sync_exchange_balances(db_session, emit_events=False)
    assert result["accounts"] == 1
    assert result["balances"] == 0
    assert result["portfolio_state"]["open_positions"] == 0
    assert db_session.scalar(select(PortfolioAction.id).limit(1)) is None


def test_portfolio_sync_emits_auto_watch_after_commit(db_session, monkeypatch) -> None:
    class WatchPlugin:
        def __init__(self, account: ExchangeAccount) -> None:
            self.account = account

        async def fetch_balances(self):
            return [{"symbol": "WATCHUSD_EVT", "balance": 8.0, "value_usd": 420.0}]

        async def fetch_positions(self):
            return []

        async def fetch_orders(self):
            return []

        async def fetch_trades(self):
            return []

    from src.apps.portfolio.clients import register_exchange

    register_exchange("fixture_watch_events", WatchPlugin)
    create_exchange_account(db_session, exchange_name="fixture_watch_events")
    published: list[str] = []
    monkeypatch.setattr("src.apps.portfolio.engine.publish_event", lambda event_type, payload: published.append(event_type))

    result = sync_exchange_balances(db_session, emit_events=True)

    assert result["status"] == "ok"
    assert published[:3] == [
        "coin_auto_watch_enabled",
        "portfolio_balance_updated",
        "portfolio_position_changed",
    ]


def test_portfolio_helper_and_event_branches(db_session, monkeypatch) -> None:
    sideways = calculate_position_size(
        total_capital=100_000.0,
        available_capital=100_000.0,
        decision_confidence=0.6,
        regime="sideways_range",
        price_current=None,
        atr_14=None,
    )
    assert sideways["regime_factor"] == 0.85
    high_volatility = calculate_position_size(
        total_capital=100_000.0,
        available_capital=100_000.0,
        decision_confidence=0.6,
        regime="high_volatility",
        price_current=100.0,
        atr_14=2.0,
    )
    assert high_volatility["regime_factor"] == 0.95
    assert calculate_position_size(
        total_capital=100_000.0,
        available_capital=100_000.0,
        decision_confidence=0.6,
        regime="unknown_regime",
        price_current=100.0,
        atr_14=2.0,
    )["regime_factor"] == 1.0
    assert calculate_stops(entry_price=0.0, atr=2.0).stop_loss is None

    position = PortfolioPosition(
        coin_id=1,
        exchange_account_id=None,
        source_exchange="fixture",
        position_type="long",
        timeframe=15,
        entry_price=0.0,
        position_size=0.0,
        position_value=0.0,
        status="closed",
    )
    action, size = _rebalance_existing_position(
        position=position,
        target_value=250.0,
        entry_price=50.0,
        decision_confidence=0.8,
        atr_14=2.5,
    )
    assert action == "OPEN_POSITION"
    assert size == 250.0
    assert position.status == "open"

    published: list[str] = []
    monkeypatch.setattr("src.apps.portfolio.engine.publish_event", lambda event_type, payload: published.append(event_type))

    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    metrics = upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bear_trend", timeframe=15)
    create_market_decision(db_session, coin_id=int(coin.id), timeframe=15, decision="BUY", confidence=0.45)
    opened = evaluate_portfolio_action(db_session, coin_id=int(coin.id), timeframe=15, emit_events=True)
    metrics.market_regime = "bull_trend"
    db_session.commit()
    create_market_decision(db_session, coin_id=int(coin.id), timeframe=15, decision="SELL", confidence=0.4)
    rebalanced = evaluate_portfolio_action(db_session, coin_id=int(coin.id), timeframe=15, emit_events=True)
    create_market_decision(db_session, coin_id=int(coin.id), timeframe=15, decision="SELL", confidence=0.8)
    closed = evaluate_portfolio_action(db_session, coin_id=int(coin.id), timeframe=15, emit_events=True)

    sell_coin = create_test_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test")
    upsert_coin_metrics(db_session, coin_id=int(sell_coin.id), regime="bull_trend", timeframe=15)
    create_market_decision(db_session, coin_id=int(sell_coin.id), timeframe=15, decision="SELL", confidence=0.7)
    sell_without_position = evaluate_portfolio_action(db_session, coin_id=int(sell_coin.id), timeframe=15, emit_events=True)

    hold_coin = create_test_coin(db_session, symbol="SOLUSD_EVT", name="Solana Event Test")
    upsert_coin_metrics(db_session, coin_id=int(hold_coin.id), regime="sideways_range", timeframe=15)
    create_market_decision(db_session, coin_id=int(hold_coin.id), timeframe=15, decision="HOLD", confidence=0.55)
    held = evaluate_portfolio_action(db_session, coin_id=int(hold_coin.id), timeframe=15, emit_events=True)

    assert opened["action"] == "OPEN_POSITION"
    assert opened["portfolio_state"]["open_positions"] >= 1
    assert opened["portfolio_state"]["updated_at"] is not None
    assert rebalanced["action"] == "REDUCE_POSITION"
    assert closed["action"] == "CLOSE_POSITION"
    assert sell_without_position["action"] == "HOLD_POSITION"
    assert held["action"] == "HOLD_POSITION"
    assert "portfolio_position_opened" in published
    assert "portfolio_rebalanced" in published
    assert "portfolio_position_closed" in published


def test_portfolio_balance_rows_update_and_reopen_positions(db_session) -> None:
    class MutablePlugin:
        value_usd = 100.0
        balance = 2.0

        def __init__(self, account: ExchangeAccount) -> None:
            self.account = account

        async def fetch_balances(self):
            return [{"symbol": "XRPUSD_EVT", "balance": self.balance, "value_usd": self.value_usd}]

        async def fetch_positions(self):
            return []

        async def fetch_orders(self):
            return []

        async def fetch_trades(self):
            return []

    from src.apps.portfolio.clients import register_exchange

    register_exchange("fixture_update", MutablePlugin)
    account = create_exchange_account(db_session, exchange_name="fixture_update")
    coin = create_test_coin(db_session, symbol="XRPUSD_EVT", name="Ripple Event Test")
    upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=1440)

    _sync_balance_position(db_session, account=account, coin=coin, value_usd=0.0, balance=0.0)
    db_session.commit()
    assert db_session.scalar(
        select(PortfolioPosition.id).where(
            PortfolioPosition.exchange_account_id == int(account.id),
            PortfolioPosition.coin_id == int(coin.id),
        )
    ) is None

    _sync_balance_position(db_session, account=account, coin=coin, value_usd=250.0, balance=5.0)
    db_session.commit()
    position = db_session.scalar(
        select(PortfolioPosition)
        .where(
            PortfolioPosition.exchange_account_id == int(account.id),
            PortfolioPosition.coin_id == int(coin.id),
        )
        .limit(1)
    )
    assert position is not None
    assert position.status == "open"

    _sync_balance_position(db_session, account=account, coin=coin, value_usd=0.0, balance=0.0)
    db_session.commit()
    db_session.refresh(position)
    assert position.status == "closed"

    _sync_balance_position(db_session, account=account, coin=coin, value_usd=300.0, balance=6.0)
    db_session.commit()
    db_session.refresh(position)
    assert position.status == "open"
    assert position.closed_at is None

    first_sync = sync_exchange_balances(db_session, emit_events=False)
    balance_row = db_session.scalar(
        select(PortfolioBalance)
        .where(
            PortfolioBalance.exchange_account_id == int(account.id),
            PortfolioBalance.symbol == "XRPUSD_EVT",
        )
        .limit(1)
    )
    assert balance_row is not None
    assert first_sync["balances"] == 1

    MutablePlugin.value_usd = 150.0
    MutablePlugin.balance = 3.0
    second_sync = sync_exchange_balances(db_session, emit_events=False)
    db_session.refresh(balance_row)
    assert second_sync["balances"] == 1
    assert float(balance_row.value_usd) == 150.0
    assert float(balance_row.balance) == 3.0
