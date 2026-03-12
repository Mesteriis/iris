from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src.apps.indicators.models import CoinMetrics, IndicatorCache
from src.apps.market_data.models import Candle, Coin
from src.apps.market_data.schemas import CandleConfig
from src.apps.market_data.service_layer import (
    BASE_TIMEFRAME_MINUTES,
    _sync_coin_history,
    bulk_create_price_history,
    calculate_backfill_progress,
    coin_has_base_candles,
    count_candle_points,
    count_price_history_points,
    create_coin,
    create_price_history,
    delete_coin,
    get_base_candle_config,
    get_coin_base_timeframe,
    get_coin_by_id,
    get_coin_by_symbol,
    get_interval_retention_bars,
    get_latest_history_timestamp,
    get_latest_price,
    get_next_pending_backfill_due_at,
    list_coins,
    list_coins_pending_backfill,
    list_coins_ready_for_latest_sync,
    list_price_history,
    prune_future_price_history,
    prune_price_history,
    publish_candle_events,
    resolve_history_interval,
    serialize_candles,
    sync_coin_history_backfill,
    sync_coin_history_backfill_forced,
    sync_coin_latest_history,
    sync_watched_assets,
)
from src.apps.market_data.sources.base import MarketBar
from tests.factories.market_data import CoinCreateFactory, PriceHistoryCreateFactory


def test_market_data_service_layer_config_and_queries(db_session, seeded_market, monkeypatch) -> None:
    fixed_now = datetime(2026, 3, 12, 1, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("src.apps.market_data.service_layer.utc_now", lambda: fixed_now)

    btc = get_coin_by_symbol(db_session, "BTCUSD_EVT")
    assert btc is not None

    default_coin = Coin(
        symbol="DEFAULT_EVT",
        name="Default Asset",
        asset_type="crypto",
        theme="core",
        source="fixture",
        enabled=True,
        sort_order=0,
        sector_code="core",
        candles_config=[],
    )
    assert get_base_candle_config(default_coin) == {"interval": "15m", "retention_bars": 20160}

    serialized = serialize_candles(
        [
            CandleConfig(interval="1h", retention_bars=10),
            {"interval": "15m", "retention_bars": 20},
        ]
    )
    assert serialized[0]["interval"] == "1h"
    assert get_base_candle_config(btc)["interval"] == "15m"
    assert get_interval_retention_bars(btc, "1d") == 3650
    assert get_interval_retention_bars(btc, "15m") == 20160
    assert get_coin_base_timeframe(btc) == BASE_TIMEFRAME_MINUTES
    assert resolve_history_interval(btc) == "15m"
    assert resolve_history_interval(btc, " 1H ") == "1h"
    assert coin_has_base_candles(db_session, btc) is True

    pending_coin = create_coin(
        db_session,
        CoinCreateFactory.build(symbol="XRPUSD_EVT", name="Ripple Event Test", theme="payments"),
    )
    pending_coin.next_history_sync_at = fixed_now + timedelta(hours=1)
    db_session.commit()

    assert pending_coin in list(list_coins_pending_backfill(db_session))
    ready_symbols = {coin.symbol for coin in list_coins_ready_for_latest_sync(db_session)}
    assert {"BTCUSD_EVT", "ETHUSD_EVT", "SOLUSD_EVT"} <= ready_symbols
    monkeypatch.setattr(
        "src.apps.market_data.service_layer.list_coins_pending_backfill",
        lambda db: [pending_coin],
    )
    assert get_next_pending_backfill_due_at(db_session) == pending_coin.next_history_sync_at

    pending_coin.next_history_sync_at = fixed_now - timedelta(minutes=1)
    db_session.commit()
    assert get_next_pending_backfill_due_at(db_session) is not None

    btc.deleted_at = datetime.now(timezone.utc)
    db_session.commit()
    assert get_coin_by_symbol(db_session, "BTCUSD_EVT") is None
    assert get_coin_by_symbol(db_session, "BTCUSD_EVT", include_deleted=True) is not None
    btc.deleted_at = None
    db_session.commit()

    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr("src.apps.market_data.service_layer.publish_event", lambda event_type, payload: published.append((event_type, payload)))
    publish_candle_events(
        coin_id=int(btc.id),
        timeframe=15,
        timestamp=datetime.now(timezone.utc),
        created_count=3,
        source="manual",
    )
    assert [event_type for event_type, _ in published] == ["candle_inserted", "candle_closed"]


def test_market_data_service_layer_history_operations(db_session, seeded_market, monkeypatch) -> None:
    btc = get_coin_by_symbol(db_session, "BTCUSD_EVT")
    assert btc is not None

    history_rows = list_price_history(db_session, "BTCUSD_EVT", "15m")
    assert history_rows
    latest_before = get_latest_price(db_session, "BTCUSD_EVT", "15m")
    assert latest_before is not None
    assert get_latest_price(db_session, "MISSING_EVT") is None

    published: list[tuple[int, str]] = []
    monkeypatch.setattr(
        "src.apps.market_data.service_layer.publish_candle_events",
        lambda **kwargs: published.append((kwargs["created_count"], kwargs["source"])),
    )

    manual_payload = PriceHistoryCreateFactory.build(
        interval="15m",
        timestamp=latest_before["timestamp"] + timedelta(minutes=15),
        price=321.0,
        volume=123.0,
    )
    created = create_price_history(db_session, btc, manual_payload)
    assert created["price"] == 321.0
    assert published[-1] == (1, "manual")

    with pytest.raises(ValueError, match="base timeframe"):
        create_price_history(
            db_session,
            btc,
            PriceHistoryCreateFactory.build(interval="1h", timestamp=manual_payload.timestamp, price=1.0),
        )

    assert bulk_create_price_history(db_session, btc, "15m", []) == 0
    with pytest.raises(ValueError, match="base timeframe"):
        bulk_create_price_history(
            db_session,
            btc,
            "1h",
            [PriceHistoryCreateFactory.build(interval="1h", timestamp=manual_payload.timestamp, price=1.0)],
        )

    created_count = bulk_create_price_history(
        db_session,
        btc,
        "15m",
        [
            PriceHistoryCreateFactory.build(
                interval="15m",
                timestamp=manual_payload.timestamp + timedelta(minutes=15),
                price=400.0,
                volume=10.0,
            ),
            PriceHistoryCreateFactory.build(
                interval="15m",
                timestamp=manual_payload.timestamp + timedelta(minutes=30),
                price=410.0,
                volume=12.0,
            ),
        ],
    )
    assert created_count == 2
    assert published[-1] == (2, "bulk_manual")

    latest_timestamp = get_latest_history_timestamp(db_session, int(btc.id), "15m")
    assert latest_timestamp is not None

    future_payload = PriceHistoryCreateFactory.build(
        interval="15m",
        timestamp=latest_timestamp + timedelta(minutes=45),
        price=999.0,
        volume=1.0,
    )
    create_price_history(db_session, btc, future_payload)
    assert prune_future_price_history(db_session, btc, "15m", latest_timestamp) >= 1
    assert prune_price_history(db_session, btc, "15m", 10) >= 0

    assert count_price_history_points(
        db_session,
        int(btc.id),
        "15m",
        latest_timestamp - timedelta(hours=2),
        latest_timestamp,
    ) >= 1
    assert get_coin_by_id(db_session, int(btc.id)) == btc
    with pytest.raises(ValueError, match="was not found"):
        get_coin_by_id(db_session, 999999)

    assert count_candle_points(
        db_session,
        int(btc.id),
        15,
        latest_timestamp - timedelta(hours=2),
        latest_timestamp,
    ) >= 1

    loaded_points, total_points, progress = calculate_backfill_progress(
        db_session,
        btc,
        serialize_candles(btc.candles_config),
        latest_timestamp,
    )
    assert total_points >= loaded_points
    assert 0.0 <= progress <= 100.0


def test_market_data_service_layer_coin_lifecycle_and_sync_assets(db_session, monkeypatch) -> None:
    payload = CoinCreateFactory.build(
        symbol="ADAUSD_EVT",
        name="Cardano Event Test",
        theme="layer1",
        sector="smart_contract",
        candles=[{"interval": "15m", "retention_bars": 100}],
    )
    coin = create_coin(db_session, payload)
    assert coin.symbol == "ADAUSD_EVT"

    updated = create_coin(
        db_session,
        CoinCreateFactory.build(
            symbol="ADAUSD_EVT",
            name="Cardano Updated",
            asset_type="stock",
            theme="payments",
            sector="payments",
            source="manual",
            candles=[{"interval": "15m", "retention_bars": 150}],
        ),
    )
    assert updated.id == coin.id
    assert updated.name == "Cardano Updated"
    assert updated.asset_type == "stock"
    assert updated.history_backfill_completed_at is None

    deleted = create_coin(db_session, CoinCreateFactory.build(symbol="DOGEUSD_EVT", name="Doge Event Test"))
    deleted.deleted_at = datetime.now(timezone.utc)
    db_session.commit()

    monkeypatch.setattr(
        "src.apps.market_data.service_layer.WATCHED_ASSETS",
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
    synced = sync_watched_assets(db_session)
    assert any(row.symbol == "AVAXUSD_EVT" for row in synced)
    doge = get_coin_by_symbol(db_session, "DOGEUSD_EVT", include_deleted=True)
    assert doge is not None and doge.deleted_at is not None

    db_session.add(
        Candle(
            coin_id=int(updated.id),
            timeframe=15,
            timestamp=datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
        )
    )
    db_session.add(
        IndicatorCache(
            coin_id=int(updated.id),
            timeframe=15,
            indicator="price_current",
            timestamp=datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc),
            value=1.0,
            indicator_version=1,
            feature_source="test",
        )
    )
    db_session.commit()

    delete_coin(db_session, updated)
    assert updated.enabled is False
    assert updated.deleted_at is not None

    assert db_session.scalar(select(Candle).where(Candle.coin_id == int(updated.id)).limit(1)) is None
    assert db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(updated.id)).limit(1)) is None


def test_market_data_service_layer_sync_history_branches(db_session, monkeypatch) -> None:
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
    coin = create_coin(
        db_session,
        CoinCreateFactory.build(symbol="MATICUSD_EVT", name="Polygon Event Test", candles=[{"interval": "15m", "retention_bars": 10}]),
    )

    progress_events: list[tuple[str, object]] = []
    monkeypatch.setattr("src.apps.market_data.service_layer.utc_now", lambda: now)
    monkeypatch.setattr(
        "src.apps.market_data.service_layer.calculate_backfill_progress",
        lambda *args, **kwargs: (0, 10, 0.0),
    )
    monkeypatch.setattr("src.apps.market_data.service_layer.prune_future_price_history", lambda *args, **kwargs: 0)
    monkeypatch.setattr("src.apps.market_data.service_layer.prune_price_history", lambda *args, **kwargs: 0)
    monkeypatch.setattr("src.apps.market_data.service_layer.get_latest_history_timestamp", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.apps.market_data.service_layer.upsert_base_candles", lambda *args, **kwargs: latest_available)
    monkeypatch.setattr(
        "src.apps.market_data.service_layer.publish_coin_history_progress_message",
        lambda coin, **kwargs: progress_events.append(("progress", kwargs["progress_percent"])),
    )
    monkeypatch.setattr(
        "src.apps.market_data.service_layer.publish_coin_history_loaded_message",
        lambda coin, **kwargs: progress_events.append(("loaded", kwargs["total_points"])),
    )
    monkeypatch.setattr(
        "src.apps.market_data.service_layer.publish_coin_analysis_messages",
        lambda coin: progress_events.append(("analysis", coin.symbol)),
    )
    monkeypatch.setattr(
        "src.apps.market_data.service_layer.publish_candle_events",
        lambda **kwargs: progress_events.append(("candle", kwargs["created_count"])),
    )

    class Carousel:
        async def fetch_history_window(self, *_args, **_kwargs):
            return SimpleNamespace(bars=[bar], completed=False, error="source_backoff")

    monkeypatch.setattr("src.apps.market_data.service_layer.get_market_source_carousel", lambda: Carousel())

    backoff = sync_coin_history_backfill(db_session, coin)
    assert backoff["status"] == "backoff"
    assert coin.next_history_sync_at == now + timedelta(hours=1)
    assert coin.last_history_sync_error == "source_backoff"

    coin.next_history_sync_at = now + timedelta(hours=2)
    db_session.commit()
    deferred = sync_coin_history_backfill(db_session, coin)
    assert deferred["status"] == "deferred"

    coin.enabled = False
    db_session.commit()
    assert sync_coin_history_backfill(db_session, coin)["status"] == "skipped"
    coin.enabled = True
    coin.next_history_sync_at = now + timedelta(hours=2)
    db_session.commit()

    monkeypatch.setattr(
        "src.apps.market_data.service_layer.calculate_backfill_progress",
        lambda *args, **kwargs: (10, 10, 100.0),
    )

    class CompleteCarousel:
        async def fetch_history_window(self, *_args, **_kwargs):
            return SimpleNamespace(bars=[bar], completed=True, error=None)

    monkeypatch.setattr("src.apps.market_data.service_layer.get_market_source_carousel", lambda: CompleteCarousel())
    forced = sync_coin_history_backfill_forced(db_session, coin)
    assert forced["status"] == "ok"
    assert coin.history_backfill_completed_at == now
    assert ("loaded", 10) in progress_events
    assert ("analysis", "MATICUSD_EVT") in progress_events

    pending = create_coin(db_session, CoinCreateFactory.build(symbol="LINKUSD_EVT", name="Link Event Test"))
    assert sync_coin_latest_history(db_session, pending)["status"] == "pending_backfill"

    coin.history_backfill_completed_at = now
    db_session.commit()
    monkeypatch.setattr("src.apps.market_data.service_layer.get_latest_history_timestamp", lambda *args, **kwargs: latest_available)
    latest_result = sync_coin_latest_history(db_session, coin, force=False)
    assert latest_result["status"] == "ok"


def test_market_data_service_layer_additional_edge_branches(db_session, monkeypatch) -> None:
    base_coin = Coin(
        symbol="EDGE_EVT",
        name="Edge Asset",
        asset_type="crypto",
        theme="core",
        source="fixture",
        enabled=True,
        sort_order=1,
        sector_code="core",
        candles_config=[{"interval": "1h", "retention_bars": 48}],
    )
    assert get_interval_retention_bars(base_coin, "1d") == 48

    deleted_coin = create_coin(
        db_session,
        CoinCreateFactory.build(symbol="DELETED_EVT", name="Deleted Event Test", source="fixture"),
    )
    deleted_coin.enabled = False
    deleted_coin.deleted_at = datetime(2026, 3, 12, 8, 0, tzinfo=timezone.utc)
    db_session.commit()
    assert "DELETED_EVT" in {coin.symbol for coin in list_coins(db_session, include_deleted=True)}
    assert "DELETED_EVT" not in {coin.symbol for coin in list_coins(db_session, enabled_only=True, include_deleted=True)}

    preserve_coin = create_coin(
        db_session,
        CoinCreateFactory.build(symbol="PRESERVE_EVT", name="Preserve Event Test", source="fixture"),
    )
    preserve_coin.history_backfill_completed_at = datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc)
    preserve_coin.last_history_sync_at = datetime(2026, 3, 12, 9, 15, tzinfo=timezone.utc)
    preserve_coin.last_history_sync_error = "old"
    db_session.commit()
    updated = create_coin(
        db_session,
        CoinCreateFactory.build(symbol="PRESERVE_EVT", name="Preserve Renamed", source="fixture"),
    )
    assert list_coins_pending_backfill(db_session, symbol="preserve_evt") == [updated]
    assert updated.history_backfill_completed_at is not None
    assert updated.last_history_sync_error == "old"

    monkeypatch.setattr("src.apps.market_data.service_layer.fetch_candle_points", lambda *args, **kwargs: [])
    assert get_latest_price(db_session, "PRESERVE_EVT") is None
    assert list_price_history(db_session, "MISSING_EDGE_EVT") == []

    monkeypatch.setattr("src.apps.market_data.service_layer.get_latest_candle_timestamp", lambda *args, **kwargs: None)
    assert prune_price_history(db_session, updated, "15m", 10) == 0


def test_market_data_service_layer_sync_history_progress_update_and_latest_none(monkeypatch) -> None:
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    latest_available = now - timedelta(minutes=15)
    coin = SimpleNamespace(
        id=1,
        symbol="SYNC_EVT",
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
        def commit(self) -> None:
            return None

        def refresh(self, _coin) -> None:
            return None

    class Carousel:
        async def fetch_history_window(self, coin_obj, interval: str, start: datetime, end: datetime):
            fetch_calls.append((interval, start))
            return SimpleNamespace(bars=[bar], completed=True, error=None)

    monkeypatch.setattr("src.apps.market_data.service_layer.utc_now", lambda: now)
    monkeypatch.setattr("src.apps.market_data.service_layer.calculate_backfill_progress", lambda *args, **kwargs: next(progress_values))
    monkeypatch.setattr("src.apps.market_data.service_layer.latest_completed_timestamp", lambda interval, reference: latest_available)
    monkeypatch.setattr("src.apps.market_data.service_layer.history_window_start", lambda latest, interval, retention: latest - timedelta(minutes=15))
    monkeypatch.setattr("src.apps.market_data.service_layer.prune_future_price_history", lambda *args, **kwargs: 0)
    monkeypatch.setattr("src.apps.market_data.service_layer.prune_price_history", lambda *args, **kwargs: 0)
    monkeypatch.setattr("src.apps.market_data.service_layer.get_latest_history_timestamp", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.apps.market_data.service_layer.get_market_source_carousel", lambda: Carousel())
    monkeypatch.setattr("src.apps.market_data.service_layer.upsert_base_candles", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.apps.market_data.service_layer.publish_coin_history_progress_message", lambda coin, **kwargs: events.append(("progress", kwargs["progress_percent"])))
    monkeypatch.setattr("src.apps.market_data.service_layer.publish_coin_history_loaded_message", lambda coin, **kwargs: events.append(("loaded", kwargs["total_points"])))
    monkeypatch.setattr("src.apps.market_data.service_layer.publish_coin_analysis_messages", lambda coin: events.append(("analysis", coin.symbol)))
    monkeypatch.setattr("src.apps.market_data.service_layer.publish_candle_events", lambda **kwargs: events.append(("candle", kwargs["created_count"])))

    result = _sync_coin_history(FakeDb(), coin, history_mode="backfill")
    assert result == {"symbol": "SYNC_EVT", "created": 1, "status": "ok"}
    assert events == [("progress", 10.0), ("progress", 50.0), ("progress", 100.0), ("loaded", 10), ("analysis", "SYNC_EVT")]

    coin.history_backfill_completed_at = now
    events.clear()
    latest_result = _sync_coin_history(FakeDb(), coin, history_mode="latest", force=True)
    assert latest_result["status"] == "ok"
    assert fetch_calls[-1] == ("15m", latest_available)
    assert events == []
