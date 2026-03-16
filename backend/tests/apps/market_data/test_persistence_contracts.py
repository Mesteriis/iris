import importlib.util
from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest
import src.apps.market_data.services as market_data_services_module
import src.apps.market_data.tasks as market_data_tasks_module
from src.apps.market_data.query_services import MarketDataQueryService
from src.apps.market_data.schemas import CoinCreate, PriceHistoryCreate
from src.apps.market_data.services import MarketDataService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_market_data_query_returns_immutable_read_models(async_db_session, seeded_market) -> None:
    latest_timestamp = seeded_market["BTCUSD_EVT"]["latest_timestamp"]
    assert latest_timestamp is not None

    async with SessionUnitOfWork(async_db_session) as uow:
        created = await MarketDataService(uow).create_coin(
            CoinCreate(
                symbol="ATOMUSD_EVT",
                name="Cosmos Event Test",
                asset_type="crypto",
                theme="layer1",
                sector="infrastructure",
                source="fixture",
                sort_order=7,
                candles=[{"interval": "15m", "retention_bars": 120}],
            )
        )
        created_history = await MarketDataService(uow).create_price_history(
            symbol=created.symbol,
            payload=PriceHistoryCreate(
                interval="15m",
                timestamp=latest_timestamp + timedelta(minutes=15),
                price=14.25,
                volume=55.0,
            ),
        )
        coins = await MarketDataQueryService(uow.session).list_coins()
        history = await MarketDataQueryService(uow.session).list_price_history(created.symbol, "15m")

    coin = next(item for item in coins if item.symbol == created.symbol)
    assert created_history is not None
    assert len(history) == 1
    assert history[0].price == 14.25
    assert coin.symbol == "ATOMUSD_EVT"
    assert coin.candles[0].interval == "15m"
    with pytest.raises(FrozenInstanceError):
        coin.symbol = "changed"
    with pytest.raises(FrozenInstanceError):
        coin.candles[0].retention_bars = 1
    with pytest.raises(FrozenInstanceError):
        history[0].price = 0.0


@pytest.mark.asyncio
async def test_market_data_persistence_logs_cover_query_repo_and_uow(async_db_session, monkeypatch) -> None:
    events: list[str] = []

    def _debug(message: str, *args, **kwargs) -> None:
        del args, kwargs
        events.append(message)

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    monkeypatch.setattr(PERSISTENCE_LOGGER, "debug", _debug)
    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)

    async with SessionUnitOfWork(async_db_session) as uow:
        await MarketDataService(uow).create_coin(
            CoinCreate(
                symbol="NEARUSD_EVT",
                name="Near Event Test",
                asset_type="crypto",
                theme="layer1",
                sector="infrastructure",
                source="fixture",
                sort_order=8,
                candles=[{"interval": "15m", "retention_bars": 240}],
            )
        )
        items = await MarketDataQueryService(uow.session).list_coins()
        await uow.commit()

    assert items
    assert "uow.begin" in events
    assert "repo.add_market_data_coin" in events
    assert "query.list_market_data_coins" in events
    assert "uow.commit" in events


def test_market_data_services_export_no_public_async_session_wrappers() -> None:
    forbidden_exports = (
        "AGGREGATE_VIEW_BY_TIMEFRAME",
        "BASE_TIMEFRAME_MINUTES",
        "CandlePoint",
        "align_timeframe_timestamp",
        "align_timestamp",
        "candle_close_timestamp",
        "coin_has_base_candles",
        "count_candle_points",
        "count_price_history_points",
        "create_coin",
        "create_price_history",
        "create_coin_async",
        "delete_coin",
        "delete_coin_async",
        "fetch_candle_points",
        "fetch_candle_points_between",
        "get_base_candle_config",
        "get_coin_base_timeframe",
        "get_coin_by_id",
        "get_coin_by_symbol",
        "get_coin_by_symbol_async",
        "get_interval_retention_bars",
        "get_latest_candle_timestamp",
        "get_latest_history_timestamp",
        "get_latest_price",
        "get_next_pending_backfill_due_at",
        "history_window_start",
        "interval_delta",
        "interval_to_timeframe",
        "latest_completed_timestamp",
        "list_coins_pending_backfill",
        "list_coins_ready_for_latest_sync",
        "list_price_history",
        "list_coins_async",
        "list_price_history_async",
        "normalize_interval",
        "prune_future_price_history",
        "prune_price_history",
        "resolve_history_interval",
        "serialize_candles",
        "sync_watched_assets",
        "create_price_history_async",
        "get_next_pending_backfill_due_at_async",
        "list_coin_symbols_pending_backfill_async",
        "list_coin_symbols_ready_for_latest_sync_async",
        "sync_watched_assets_async",
        "sync_coin_history_backfill_async",
        "sync_coin_history_backfill_forced_async",
        "sync_coin_latest_history_async",
        "timeframe_delta",
        "upsert_base_candles",
        "utc_now",
    )

    for export_name in forbidden_exports:
        assert not hasattr(market_data_services_module, export_name), export_name


def test_market_data_tasks_export_no_wrapper_helpers() -> None:
    forbidden_exports = (
        "AsyncSessionLocal",
        "get_next_pending_backfill_due_at_async",
        "list_coin_symbols_pending_backfill_async",
        "list_coin_symbols_ready_for_latest_sync_async",
        "get_coin_by_symbol_async",
        "sync_watched_assets_async",
        "sync_coin_history_backfill_async",
        "sync_coin_history_backfill_forced_async",
        "sync_coin_latest_history_async",
    )

    for export_name in forbidden_exports:
        assert not hasattr(market_data_tasks_module, export_name), export_name


def test_market_data_legacy_views_module_is_absent() -> None:
    assert importlib.util.find_spec("src.apps.market_data.views") is None


def test_market_data_legacy_sync_repos_module_is_absent() -> None:
    assert importlib.util.find_spec("src.apps.market_data.repos") is None
