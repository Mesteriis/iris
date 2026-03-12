from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.apps.indicators.models import CoinMetrics
from app.apps.market_data.models import Coin
from app.apps.market_data.services import (
    _calculate_backfill_progress_async,
    _coin_has_base_candles_async,
    _get_latest_candle_timestamp_async,
    _get_latest_history_timestamp_async,
    _prune_future_price_history_async,
    _prune_price_history_async,
    _refresh_continuous_aggregate_range_async,
    _sync_coin_history_async,
    _upsert_base_candles_async,
    create_coin_async,
    create_price_history_async,
    delete_coin_async,
    get_coin_by_symbol_async,
    get_next_pending_backfill_due_at_async,
    list_coin_symbols_pending_backfill_async,
    list_coin_symbols_ready_for_latest_sync_async,
    list_coins_async,
    list_price_history_async,
    sync_coin_history_backfill_async,
    sync_coin_history_backfill_forced_async,
    sync_coin_latest_history_async,
    sync_watched_assets_async,
)
from app.apps.market_data.sources.base import MarketBar
from tests.factories.market_data import CoinCreateFactory, PriceHistoryCreateFactory


class _AsyncContext:
    def __init__(self, db) -> None:
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.mark.asyncio
async def test_market_data_async_services_create_query_delete_and_refresh(async_db_session, monkeypatch) -> None:
    executed: list[dict[str, object]] = []

    class AsyncConnection:
        async def execution_options(self, **kwargs):
            return self

        async def execute(self, _stmt, params):
            executed.append(params)

    class AsyncEngineContext:
        async def __aenter__(self):
            return AsyncConnection()

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    class AsyncEngine:
        def connect(self):
            return AsyncEngineContext()

    monkeypatch.setattr("app.apps.market_data.services.async_engine", AsyncEngine())

    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    await _refresh_continuous_aggregate_range_async(timeframe=17, window_start=now, window_end=now)
    await _refresh_continuous_aggregate_range_async(timeframe=60, window_start=now, window_end=now)
    assert executed[0]["view_name"] == "candles_1h"

    created = await create_coin_async(
        async_db_session,
        CoinCreateFactory.build(symbol="ADAUSD_EVT", name="Cardano Event Test"),
    )
    assert created.symbol == "ADAUSD_EVT"

    updated = await create_coin_async(
        async_db_session,
        CoinCreateFactory.build(
            symbol="ADAUSD_EVT",
            name="Cardano Updated",
            asset_type="stock",
            source="manual",
            candles=[{"interval": "15m", "retention_bars": 100}],
        ),
    )
    assert updated.id == created.id
    assert updated.asset_type == "stock"

    assert await get_coin_by_symbol_async(async_db_session, "ADAUSD_EVT") is not None
    listed = await list_coins_async(async_db_session, enabled_only=True)
    assert any(coin.symbol == "ADAUSD_EVT" for coin in listed)

    metrics = await async_db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(updated.id)))
    assert metrics is not None

    await delete_coin_async(async_db_session, updated)
    assert await get_coin_by_symbol_async(async_db_session, "ADAUSD_EVT") is None
    deleted = await get_coin_by_symbol_async(async_db_session, "ADAUSD_EVT", include_deleted=True)
    assert deleted is not None and deleted.deleted_at is not None


@pytest.mark.asyncio
async def test_market_data_async_services_history_helpers(async_db_session, seeded_market, monkeypatch) -> None:
    btc = await get_coin_by_symbol_async(async_db_session, "BTCUSD_EVT")
    assert btc is not None

    latest = await _get_latest_candle_timestamp_async(async_db_session, coin_id=int(btc.id), timeframe=15)
    assert latest is not None
    assert await _coin_has_base_candles_async(async_db_session, btc) is True

    history = await list_price_history_async(async_db_session, "BTCUSD_EVT", "15m")
    assert history
    assert await list_price_history_async(async_db_session, "MISSING_EVT") == []

    published: list[tuple[int, str]] = []
    monkeypatch.setattr(
        "app.apps.market_data.services.publish_candle_events",
        lambda **kwargs: published.append((kwargs["created_count"], kwargs["source"])),
    )

    manual_payload = PriceHistoryCreateFactory.build(
        interval="15m",
        timestamp=latest + timedelta(minutes=15),
        price=321.0,
        volume=123.0,
    )
    created = await create_price_history_async(async_db_session, btc, manual_payload)
    assert created["price"] == 321.0
    assert published[-1] == (1, "manual")

    with pytest.raises(ValueError, match="base timeframe"):
        await create_price_history_async(
            async_db_session,
            btc,
            PriceHistoryCreateFactory.build(interval="1h", timestamp=manual_payload.timestamp, price=1.0),
        )

    assert await _get_latest_history_timestamp_async(async_db_session, coin_id=int(btc.id), interval="15m") is not None
    assert await _calculate_backfill_progress_async(
        async_db_session,
        coin_id=int(btc.id),
        candles=btc.candles_config,
        reference_time=latest,
    )

    assert await _calculate_backfill_progress_async(
        async_db_session,
        coin_id=999999,
        candles=[],
        reference_time=latest,
    ) == (0, 0, 0.0)

    future_payload = PriceHistoryCreateFactory.build(
        interval="15m",
        timestamp=latest + timedelta(minutes=45),
        price=999.0,
        volume=1.0,
    )
    await create_price_history_async(async_db_session, btc, future_payload)
    assert await _prune_future_price_history_async(
        async_db_session,
        coin_id=int(btc.id),
        interval="15m",
        latest_allowed=latest,
    ) >= 1
    assert await _prune_price_history_async(
        async_db_session,
        coin_id=int(btc.id),
        interval="15m",
        retention_bars=10,
    ) >= 0
    assert await _prune_price_history_async(
        async_db_session,
        coin_id=999999,
        interval="15m",
        retention_bars=10,
    ) == 0

    monkeypatch.setattr("app.apps.market_data.services._refresh_continuous_aggregate_range_async", lambda **kwargs: __import__("asyncio").sleep(0))
    bar = MarketBar(
        timestamp=latest + timedelta(minutes=15),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=50.0,
        source="fixture",
    )
    assert await _upsert_base_candles_async(async_db_session, coin_id=999999, interval="15m", bars=[bar]) is None
    assert await _upsert_base_candles_async(async_db_session, coin_id=int(btc.id), interval="15m", bars=[]) is None
    assert await _upsert_base_candles_async(async_db_session, coin_id=int(btc.id), interval="15m", bars=[bar]) == bar.timestamp


@pytest.mark.asyncio
async def test_market_data_async_services_sync_queries_and_watched_assets(async_db_session, monkeypatch) -> None:
    fixed_now = datetime(2026, 3, 12, 1, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("app.apps.market_data.services.utc_now", lambda: fixed_now)

    pending = await create_coin_async(
        async_db_session,
        CoinCreateFactory.build(symbol="XRPUSD_EVT", name="Ripple Event Test", theme="payments"),
    )
    pending.next_history_sync_at = fixed_now + timedelta(hours=1)
    await async_db_session.commit()

    monkeypatch.setattr(
        "app.apps.market_data.services._coin_has_base_candles_async",
        lambda db, coin: __import__("asyncio").sleep(0, result=coin.symbol != "XRPUSD_EVT"),
    )

    class FakePendingSession:
        async def execute(self, _stmt):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [pending]))

    monkeypatch.setattr("app.apps.market_data.services.AsyncSessionLocal", lambda: _AsyncContext(FakePendingSession()))
    assert await get_next_pending_backfill_due_at_async() == pending.next_history_sync_at

    monkeypatch.setattr("app.apps.market_data.services.AsyncSessionLocal", lambda: _AsyncContext(async_db_session))
    assert "XRPUSD_EVT" in await list_coin_symbols_pending_backfill_async(async_db_session)
    assert await list_coin_symbols_pending_backfill_async(async_db_session, symbol="xrpusd_evt") == ["XRPUSD_EVT"]

    pending.history_backfill_completed_at = fixed_now
    await async_db_session.commit()
    monkeypatch.setattr(
        "app.apps.market_data.services._coin_has_base_candles_async",
        lambda db, coin: __import__("asyncio").sleep(0, result=True),
    )
    assert "XRPUSD_EVT" in await list_coin_symbols_ready_for_latest_sync_async(async_db_session)

    monkeypatch.setattr(
        "app.apps.market_data.services.WATCHED_ASSETS",
        [
            {
                "symbol": "DOGEUSD_EVT",
                "name": "Doge Event Test",
                "asset_type": "crypto",
                "theme": "memes",
                "source": "fixture",
                "enabled": True,
                "order": 9,
                "candles": [{"interval": "15m", "retention_bars": 200}],
            },
            {
                "symbol": "AVAXUSD_EVT",
                "name": "Avalanche Event Test",
                "asset_type": "crypto",
                "theme": "layer1",
                "source": "fixture",
                "enabled": True,
                "order": 10,
                "candles": [{"interval": "15m", "retention_bars": 200}],
            },
        ],
    )
    deleted = await create_coin_async(async_db_session, CoinCreateFactory.build(symbol="DOGEUSD_EVT", name="Doge Event Test"))
    deleted.deleted_at = fixed_now
    await async_db_session.commit()

    synced = await sync_watched_assets_async(async_db_session)
    assert "AVAXUSD_EVT" in synced
    doge = await get_coin_by_symbol_async(async_db_session, "DOGEUSD_EVT", include_deleted=True)
    assert doge is not None and doge.deleted_at is not None


@pytest.mark.asyncio
async def test_market_data_async_services_sync_history_branches(async_db_session, monkeypatch) -> None:
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    latest_available = now - timedelta(minutes=15)
    bar = MarketBar(
        timestamp=latest_available,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=50.0,
        source="fixture",
    )
    coin = await create_coin_async(
        async_db_session,
        CoinCreateFactory.build(symbol="MATICUSD_EVT", name="Polygon Event Test", candles=[{"interval": "15m", "retention_bars": 10}]),
    )

    events: list[tuple[str, object]] = []
    monkeypatch.setattr("app.apps.market_data.services.utc_now", lambda: now)
    monkeypatch.setattr(
        "app.apps.market_data.services._calculate_backfill_progress_async",
        lambda *args, **kwargs: __import__("asyncio").sleep(0, result=(0, 10, 0.0)),
    )
    monkeypatch.setattr("app.apps.market_data.services._prune_future_price_history_async", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=0))
    monkeypatch.setattr("app.apps.market_data.services._prune_price_history_async", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=0))
    monkeypatch.setattr("app.apps.market_data.services._get_latest_history_timestamp_async", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=None))
    monkeypatch.setattr("app.apps.market_data.services._upsert_base_candles_async", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=latest_available))
    monkeypatch.setattr(
        "app.apps.market_data.services.publish_coin_history_progress_message",
        lambda coin, **kwargs: events.append(("progress", kwargs["progress_percent"])),
    )
    monkeypatch.setattr(
        "app.apps.market_data.services.publish_coin_history_loaded_message",
        lambda coin, **kwargs: events.append(("loaded", kwargs["total_points"])),
    )
    monkeypatch.setattr(
        "app.apps.market_data.services.publish_coin_analysis_messages",
        lambda coin: events.append(("analysis", coin.symbol)),
    )
    monkeypatch.setattr(
        "app.apps.market_data.services.publish_candle_events",
        lambda **kwargs: events.append(("candle", kwargs["created_count"])),
    )

    class Carousel:
        async def fetch_history_window(self, *_args, **_kwargs):
            return SimpleNamespace(bars=[bar], completed=False, error="source_backoff")

    monkeypatch.setattr("app.apps.market_data.services.get_market_source_carousel", lambda: Carousel())

    backoff = await sync_coin_history_backfill_async(async_db_session, coin)
    assert backoff["status"] == "backoff"
    assert coin.next_history_sync_at == now + timedelta(hours=1)
    assert coin.last_history_sync_error == "source_backoff"

    coin.next_history_sync_at = now + timedelta(hours=2)
    await async_db_session.commit()
    deferred = await sync_coin_history_backfill_async(async_db_session, coin)
    assert deferred["status"] == "deferred"

    coin.enabled = False
    await async_db_session.commit()
    assert (await sync_coin_history_backfill_async(async_db_session, coin))["status"] == "skipped"
    coin.enabled = True
    coin.next_history_sync_at = now + timedelta(hours=2)
    await async_db_session.commit()

    monkeypatch.setattr(
        "app.apps.market_data.services._calculate_backfill_progress_async",
        lambda *args, **kwargs: __import__("asyncio").sleep(0, result=(10, 10, 100.0)),
    )

    class CompleteCarousel:
        async def fetch_history_window(self, *_args, **_kwargs):
            return SimpleNamespace(bars=[bar], completed=True, error=None)

    monkeypatch.setattr("app.apps.market_data.services.get_market_source_carousel", lambda: CompleteCarousel())
    forced = await sync_coin_history_backfill_forced_async(async_db_session, coin)
    assert forced["status"] == "ok"
    assert coin.history_backfill_completed_at == now
    assert ("loaded", 10) in events
    assert ("analysis", "MATICUSD_EVT") in events

    pending = await create_coin_async(async_db_session, CoinCreateFactory.build(symbol="LINKUSD_EVT", name="Link Event Test"))
    assert (await sync_coin_latest_history_async(async_db_session, pending))["status"] == "pending_backfill"

    coin.history_backfill_completed_at = now
    await async_db_session.commit()
    monkeypatch.setattr("app.apps.market_data.services._get_latest_history_timestamp_async", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=latest_available))
    latest_result = await sync_coin_latest_history_async(async_db_session, coin, force=False)
    assert latest_result["status"] == "ok"


@pytest.mark.asyncio
async def test_market_data_async_services_additional_edge_branches(async_db_session, monkeypatch) -> None:
    deleted = await create_coin_async(
        async_db_session,
        CoinCreateFactory.build(symbol="DLTASYNC_EVT", name="Deleted Async Test", source="fixture"),
    )
    deleted.enabled = False
    deleted.deleted_at = datetime(2026, 3, 12, 8, 0, tzinfo=timezone.utc)
    await async_db_session.commit()
    assert "DLTASYNC_EVT" in {coin.symbol for coin in await list_coins_async(async_db_session, include_deleted=True)}
    assert "DLTASYNC_EVT" not in {coin.symbol for coin in await list_coins_async(async_db_session, enabled_only=True, include_deleted=True)}

    preserve = await create_coin_async(
        async_db_session,
        CoinCreateFactory.build(symbol="PRSASYNC_EVT", name="Async Preserve", source="fixture"),
    )
    preserve.history_backfill_completed_at = datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc)
    preserve.last_history_sync_at = datetime(2026, 3, 12, 9, 15, tzinfo=timezone.utc)
    preserve.last_history_sync_error = "old"
    await async_db_session.commit()
    same_settings = await create_coin_async(
        async_db_session,
        CoinCreateFactory.build(symbol="PRSASYNC_EVT", name="Async Preserve Renamed", source="fixture"),
    )
    assert same_settings.history_backfill_completed_at is not None
    assert same_settings.last_history_sync_error == "old"

    monkeypatch.setattr(
        "app.apps.market_data.services.AsyncSessionLocal",
        lambda: _AsyncContext(type("EmptyDb", (), {"execute": lambda self, stmt: __import__("asyncio").sleep(0, result=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [])))})()),
    )
    assert await get_next_pending_backfill_due_at_async() is None

    due_coin = SimpleNamespace(symbol="DUE_EVT", history_backfill_completed_at=None, next_history_sync_at=None)
    monkeypatch.setattr(
        "app.apps.market_data.services.AsyncSessionLocal",
        lambda: _AsyncContext(type("DueDb", (), {"execute": lambda self, stmt: __import__("asyncio").sleep(0, result=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [due_coin])))})()),
    )
    monkeypatch.setattr("app.apps.market_data.services.utc_now", lambda: datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc))
    assert await get_next_pending_backfill_due_at_async() == datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)

    ready_coin = SimpleNamespace(symbol="READY_EVT", history_backfill_completed_at=datetime(2026, 3, 12, 11, 0, tzinfo=timezone.utc), next_history_sync_at=None)
    monkeypatch.setattr(
        "app.apps.market_data.services.AsyncSessionLocal",
        lambda: _AsyncContext(type("ReadyDb", (), {"execute": lambda self, stmt: __import__("asyncio").sleep(0, result=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [ready_coin])))})()),
    )
    monkeypatch.setattr(
        "app.apps.market_data.services._coin_has_base_candles_async",
        lambda db, coin: __import__("asyncio").sleep(0, result=True),
    )
    assert await get_next_pending_backfill_due_at_async() is None

    watch_coin = await create_coin_async(
        async_db_session,
        CoinCreateFactory.build(symbol="WATCH_EVT", name="Watch Coin", source="fixture"),
    )
    watch_coin.history_backfill_completed_at = datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc)
    watch_coin.last_history_sync_at = datetime(2026, 3, 12, 9, 15, tzinfo=timezone.utc)
    watch_coin.next_history_sync_at = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    watch_coin.last_history_sync_error = "old"
    await async_db_session.commit()

    monkeypatch.setattr(
        "app.apps.market_data.services.WATCHED_ASSETS",
        [
            {
                "symbol": "WATCH_EVT",
                "name": "Watch Coin Updated",
                "asset_type": "stock",
                "theme": "macro",
                "source": "manual",
                "enabled": True,
                "order": 11,
                "candles": [{"interval": "15m", "retention_bars": 120}],
            }
        ],
    )
    synced = await sync_watched_assets_async(async_db_session)
    await async_db_session.refresh(watch_coin)
    assert "WATCH_EVT" in synced
    assert watch_coin.asset_type == "stock"
    assert watch_coin.history_backfill_completed_at is None
    assert watch_coin.last_history_sync_error is None

    watch_coin.history_backfill_completed_at = datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc)
    watch_coin.last_history_sync_at = datetime(2026, 3, 12, 9, 15, tzinfo=timezone.utc)
    watch_coin.next_history_sync_at = datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc)
    watch_coin.last_history_sync_error = "preserve"
    await async_db_session.commit()
    monkeypatch.setattr(
        "app.apps.market_data.services.WATCHED_ASSETS",
        [
            {
                "symbol": "WATCH_EVT",
                "name": "Watch Coin Updated",
                "asset_type": "stock",
                "theme": "macro",
                "source": "manual",
                "enabled": True,
                "order": 11,
                "candles": [{"interval": "15m", "retention_bars": 120}],
            }
        ],
    )
    await sync_watched_assets_async(async_db_session)
    await async_db_session.refresh(watch_coin)
    assert watch_coin.history_backfill_completed_at is not None
    assert watch_coin.last_history_sync_error == "preserve"

    monkeypatch.setattr(
        "app.apps.market_data.services._coin_has_base_candles_async",
        lambda db, coin: __import__("asyncio").sleep(0, result=False),
    )
    assert await list_coin_symbols_ready_for_latest_sync_async(async_db_session) == []

    latest = await _get_latest_candle_timestamp_async(async_db_session, coin_id=int(watch_coin.id), timeframe=15)
    if latest is None:
        latest = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
        await create_price_history_async(
            async_db_session,
            watch_coin,
            PriceHistoryCreateFactory.build(interval="15m", timestamp=latest, price=123.0, volume=5.0),
        )
    older_bar = MarketBar(
        timestamp=latest - timedelta(minutes=15),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
        source="fixture",
    )
    monkeypatch.setattr("app.apps.market_data.services._refresh_continuous_aggregate_range_async", lambda **kwargs: __import__("asyncio").sleep(0))
    assert await _upsert_base_candles_async(async_db_session, coin_id=int(watch_coin.id), interval="15m", bars=[older_bar]) is None
    one_hour_bar = MarketBar(
        timestamp=latest,
        open=120.0,
        high=121.0,
        low=119.0,
        close=120.5,
        volume=6.0,
        source="fixture",
    )
    assert await _upsert_base_candles_async(async_db_session, coin_id=int(watch_coin.id), interval="1h", bars=[one_hour_bar]) == latest

@pytest.mark.asyncio
async def test_market_data_async_services_sync_history_progress_update_and_latest_none(monkeypatch) -> None:
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    latest_available = now - timedelta(minutes=15)
    coin = SimpleNamespace(
        id=1,
        symbol="ASYNC_SYNC_EVT",
        enabled=True,
        deleted_at=None,
        candles_config=[{"interval": "15m", "retention_bars": 10}],
        next_history_sync_at=None,
        history_backfill_completed_at=None,
        last_history_sync_at=None,
        last_history_sync_error=None,
    )
    bar = MarketBar(
        timestamp=latest_available,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
        source="fixture",
    )
    progress_values = iter([(1, 10, 10.0), (5, 10, 50.0), (10, 10, 100.0)])
    events: list[tuple[str, object]] = []
    fetch_calls: list[tuple[str, datetime]] = []

    class FakeDb:
        async def commit(self) -> None:
            return None

        async def refresh(self, _coin) -> None:
            return None

    class Carousel:
        async def fetch_history_window(self, coin_obj, interval: str, start: datetime, end: datetime):
            fetch_calls.append((interval, start))
            return SimpleNamespace(bars=[bar], completed=True, error=None)

    monkeypatch.setattr("app.apps.market_data.services.utc_now", lambda: now)
    monkeypatch.setattr("app.apps.market_data.services._calculate_backfill_progress_async", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=next(progress_values)))
    monkeypatch.setattr("app.apps.market_data.services.latest_completed_timestamp", lambda interval, reference: latest_available)
    monkeypatch.setattr("app.apps.market_data.services.history_window_start", lambda latest, interval, retention: latest - timedelta(minutes=15))
    monkeypatch.setattr("app.apps.market_data.services._prune_future_price_history_async", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=0))
    monkeypatch.setattr("app.apps.market_data.services._prune_price_history_async", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=0))
    monkeypatch.setattr("app.apps.market_data.services._get_latest_history_timestamp_async", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=None))
    monkeypatch.setattr("app.apps.market_data.services.get_market_source_carousel", lambda: Carousel())
    monkeypatch.setattr("app.apps.market_data.services._upsert_base_candles_async", lambda *args, **kwargs: __import__("asyncio").sleep(0, result=None))
    monkeypatch.setattr("app.apps.market_data.services.publish_coin_history_progress_message", lambda coin, **kwargs: events.append(("progress", kwargs["progress_percent"])))
    monkeypatch.setattr("app.apps.market_data.services.publish_coin_history_loaded_message", lambda coin, **kwargs: events.append(("loaded", kwargs["total_points"])))
    monkeypatch.setattr("app.apps.market_data.services.publish_coin_analysis_messages", lambda coin: events.append(("analysis", coin.symbol)))
    monkeypatch.setattr("app.apps.market_data.services.publish_candle_events", lambda **kwargs: events.append(("candle", kwargs["created_count"])))

    result = await _sync_coin_history_async(FakeDb(), coin, history_mode="backfill")
    assert result == {"symbol": "ASYNC_SYNC_EVT", "created": 1, "status": "ok"}
    assert events == [("progress", 10.0), ("progress", 50.0), ("progress", 100.0), ("loaded", 10), ("analysis", "ASYNC_SYNC_EVT")]

    coin.history_backfill_completed_at = now
    events.clear()
    latest_result = await _sync_coin_history_async(FakeDb(), coin, history_mode="latest", force=True)
    assert latest_result["status"] == "ok"
    assert fetch_calls[-1] == ("15m", latest_available)
    assert events == []
