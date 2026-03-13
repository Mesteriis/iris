from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError

from src.apps.market_data.models import Coin
from src.apps.market_data.repos import (
    BASE_TIMEFRAME_MINUTES,
    CandlePoint,
    _fetch_direct_candle_points,
    _fetch_resampled_candle_points,
    _fetch_resampled_candle_points_between,
    _fetch_view_candle_points,
    _fetch_view_candle_points_between,
    aggregate_has_rows,
    align_timeframe_timestamp,
    candle_close_timestamp,
    fetch_candle_points,
    fetch_candle_points_between,
    get_base_candle_bounds,
    get_lowest_available_candle_timeframe,
    get_latest_candle_timestamp,
    interval_to_timeframe,
    refresh_continuous_aggregate_range,
    refresh_continuous_aggregate_window,
    timeframe_bucket_interval,
    timeframe_delta,
    upsert_base_candles,
)
from src.apps.market_data.sources.base import MarketBar
from src.core.db.persistence import PERSISTENCE_LOGGER


def test_market_data_repos_direct_paths(db_session, seeded_market) -> None:
    coin = db_session.scalar(select(Coin).where(Coin.symbol == "BTCUSD_EVT"))
    assert coin is not None

    latest = get_latest_candle_timestamp(db_session, int(coin.id), BASE_TIMEFRAME_MINUTES)
    assert latest is not None

    assert timeframe_bucket_interval(60) == "1 hour"
    assert timeframe_bucket_interval(240) == "4 hours"
    assert timeframe_delta(15) == timedelta(minutes=15)
    assert interval_to_timeframe("1h") == 60
    assert align_timeframe_timestamp(latest + timedelta(minutes=7), 15) == latest
    assert candle_close_timestamp(latest, 15) == latest + timedelta(minutes=15)

    points = fetch_candle_points(db_session, int(coin.id), 15, 5)
    assert len(points) == 5
    assert points[-1].timestamp == latest

    between = fetch_candle_points_between(
        db_session,
        int(coin.id),
        15,
        latest - timedelta(hours=1),
        latest,
    )
    assert between
    assert between[-1].timestamp == latest

    first_timestamp, last_timestamp = get_base_candle_bounds(db_session, int(coin.id))
    assert first_timestamp is not None
    assert last_timestamp == latest
    assert aggregate_has_rows(db_session, int(coin.id), 17) is False

    assert upsert_base_candles(db_session, coin, "15m", []) is None

    new_bar = MarketBar(
        timestamp=latest + timedelta(minutes=15),
        open=101.0,
        high=103.0,
        low=99.0,
        close=102.0,
        volume=10_000.0,
        source="test",
    )
    assert upsert_base_candles(db_session, coin, "15m", [new_bar]) == new_bar.timestamp
    assert get_latest_candle_timestamp(db_session, int(coin.id), 15) == new_bar.timestamp


def test_market_data_repos_fallback_and_refresh_paths(monkeypatch) -> None:
    point = CandlePoint(
        timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
        open=100.0,
        high=110.0,
        low=95.0,
        close=105.0,
        volume=12.0,
    )

    monkeypatch.setattr("src.apps.market_data.repos._fetch_direct_candle_points", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.apps.market_data.repos._fetch_view_candle_points", lambda *args, **kwargs: [point])
    assert fetch_candle_points(object(), 1, 60, 5) == [point]

    monkeypatch.setattr("src.apps.market_data.repos._fetch_view_candle_points", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.apps.market_data.repos.get_lowest_available_candle_timeframe", lambda *args, **kwargs: 15)
    monkeypatch.setattr("src.apps.market_data.repos._fetch_resampled_candle_points", lambda *args, **kwargs: [point])
    assert fetch_candle_points(object(), 1, 60, 5) == [point]
    assert fetch_candle_points(object(), 1, 60, 0) == []

    monkeypatch.setattr("src.apps.market_data.repos._fetch_direct_candle_points_between", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.apps.market_data.repos._fetch_view_candle_points_between", lambda *args, **kwargs: [point])
    assert fetch_candle_points_between(object(), 1, 60, point.timestamp, point.timestamp) == [point]

    monkeypatch.setattr("src.apps.market_data.repos._fetch_view_candle_points_between", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "src.apps.market_data.repos._fetch_resampled_candle_points_between",
        lambda *args, **kwargs: [point],
    )
    assert fetch_candle_points_between(object(), 1, 60, point.timestamp, point.timestamp) == [point]

    class ScalarDb:
        def __init__(self, scalar_value, row):
            self.scalar_value = scalar_value
            self.row = row

        def scalar(self, _stmt):
            return self.scalar_value

        def execute(self, _stmt, _params=None):
            return SimpleNamespace(first=lambda: self.row)

    direct_db = ScalarDb(point.timestamp, None)
    assert get_latest_candle_timestamp(direct_db, 1, 15) == point.timestamp

    aggregate_db = ScalarDb(None, SimpleNamespace(bucket=point.timestamp))
    assert get_latest_candle_timestamp(aggregate_db, 1, 60) == point.timestamp

    monkeypatch.setattr("src.apps.market_data.repos.get_lowest_available_candle_timeframe", lambda *args, **kwargs: 15)
    monkeypatch.setattr("src.apps.market_data.repos._fetch_resampled_candle_points", lambda *args, **kwargs: [point])
    resampled_db = ScalarDb(None, SimpleNamespace(bucket=None))
    assert get_latest_candle_timestamp(resampled_db, 1, 60) == point.timestamp
    assert get_latest_candle_timestamp(resampled_db, 1, 17) is None

    class AggregateDb:
        def __init__(self, row) -> None:
            self.row = row

        def execute(self, _stmt, _params=None):
            return SimpleNamespace(first=lambda: self.row)

    assert aggregate_has_rows(AggregateDb(SimpleNamespace(value=1)), 1, 60) is True
    assert aggregate_has_rows(AggregateDb(None), 1, 60) is False

    executed: list[tuple[str, dict[str, object]]] = []

    class Connection:
        def execution_options(self, **kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _stmt, params):
            executed.append(("execute", params))

    class Bind:
        def connect(self):
            return Connection()

    class RefreshDb:
        def get_bind(self):
            return Bind()

    refresh_continuous_aggregate_range(
        RefreshDb(),
        60,
        point.timestamp,
        point.timestamp + timedelta(hours=1),
    )
    assert executed[0][1]["view_name"] == "candles_1h"

    forwarded: list[tuple[int, datetime]] = []
    monkeypatch.setattr(
        "src.apps.market_data.repos.refresh_continuous_aggregate_range",
        lambda db, timeframe, window_start, window_end: forwarded.append((timeframe, window_start)),
    )
    refresh_continuous_aggregate_window(object(), 60, point.timestamp + timedelta(minutes=17))
    refresh_continuous_aggregate_window(object(), 17, point.timestamp)

    assert forwarded == [(60, align_timeframe_timestamp(point.timestamp + timedelta(minutes=17), 60))]


def test_market_data_repos_helper_and_guard_branches(monkeypatch) -> None:
    point = CandlePoint(
        timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
        open=100.0,
        high=110.0,
        low=95.0,
        close=105.0,
        volume=12.0,
    )
    raw_row = SimpleNamespace(
        timestamp=point.timestamp,
        bucket=point.timestamp,
        open=point.open,
        high=point.high,
        low=point.low,
        close=point.close,
        volume=point.volume,
    )

    class RowsDb:
        def __init__(self, rows, scalar_value=None, first_row=None):
            self.rows = rows
            self.scalar_value = scalar_value
            self.first_row = first_row
            self.commits = 0

        def execute(self, _stmt, _params=None):
            return SimpleNamespace(
                all=lambda: self.rows,
                first=lambda: self.first_row,
            )

        def scalar(self, _stmt):
            return self.scalar_value

        def commit(self):
            self.commits += 1

        def get_bind(self):
            raise AssertionError("bind should not be requested in this branch")

    assert timeframe_bucket_interval(1440) == "1 day"
    direct_rows = [SimpleNamespace(**raw_row.__dict__), SimpleNamespace(**raw_row.__dict__)]
    assert len(_fetch_direct_candle_points(RowsDb(direct_rows), 1, 15, None)) == 2
    assert _fetch_view_candle_points(RowsDb([raw_row]), 1, 60, None) == [point]
    assert _fetch_view_candle_points(RowsDb([raw_row]), 1, 60, 1) == [point]
    assert _fetch_view_candle_points_between(RowsDb([raw_row]), 1, 60, point.timestamp, point.timestamp) == [point]
    assert _fetch_resampled_candle_points(RowsDb([raw_row]), 1, 15, 60, None) == [point]
    assert _fetch_resampled_candle_points(RowsDb([raw_row]), 1, 15, 60, 1) == [point]
    assert _fetch_resampled_candle_points_between(RowsDb([raw_row]), 1, 15, 60, point.timestamp, point.timestamp) == [point]
    assert get_lowest_available_candle_timeframe(RowsDb([], scalar_value=15), 1, max_timeframe=60) == 15
    assert get_lowest_available_candle_timeframe(RowsDb([], scalar_value=None), 1) is None

    monkeypatch.setattr("src.apps.market_data.repos._fetch_direct_candle_points", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.apps.market_data.repos._fetch_view_candle_points", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.apps.market_data.repos.get_lowest_available_candle_timeframe", lambda *args, **kwargs: None)
    assert fetch_candle_points(object(), 1, 60, 5) == []
    assert fetch_candle_points(object(), 1, 17, 5) == []

    monkeypatch.setattr("src.apps.market_data.repos._fetch_direct_candle_points_between", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.apps.market_data.repos._fetch_view_candle_points_between", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.apps.market_data.repos.get_lowest_available_candle_timeframe", lambda *args, **kwargs: 60)
    assert fetch_candle_points_between(object(), 1, 60, point.timestamp, point.timestamp) == []
    assert fetch_candle_points_between(object(), 1, 17, point.timestamp, point.timestamp) == []

    none_latest_db = RowsDb([], scalar_value=None, first_row=SimpleNamespace(bucket=None))
    monkeypatch.setattr("src.apps.market_data.repos.get_lowest_available_candle_timeframe", lambda *args, **kwargs: 60)
    assert get_latest_candle_timestamp(none_latest_db, 1, 60) is None
    monkeypatch.setattr("src.apps.market_data.repos._fetch_resampled_candle_points", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.apps.market_data.repos.get_lowest_available_candle_timeframe", lambda *args, **kwargs: 15)
    assert get_latest_candle_timestamp(none_latest_db, 1, 60) is None

    refresh_continuous_aggregate_range(object(), 17, point.timestamp, point.timestamp)

    coin = SimpleNamespace(id=1)
    older_bar = MarketBar(
        timestamp=point.timestamp - timedelta(minutes=15),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
        source="fixture",
    )
    monkeypatch.setattr("src.apps.market_data.repos.get_latest_candle_timestamp", lambda *args, **kwargs: point.timestamp)
    refresh_calls: list[int] = []
    monkeypatch.setattr(
        "src.apps.market_data.repos.refresh_continuous_aggregate_range",
        lambda db, timeframe, window_start, window_end: refresh_calls.append(timeframe),
    )
    upsert_db = RowsDb([])
    assert upsert_base_candles(upsert_db, coin, "15m", [older_bar]) is None
    assert upsert_base_candles(upsert_db, coin, "1h", [older_bar]) is None
    assert refresh_calls == [60, 240, 1440]


def test_market_data_repos_timescale_fallback_logs_and_skips(monkeypatch) -> None:
    point = CandlePoint(
        timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
        open=100.0,
        high=110.0,
        low=95.0,
        close=105.0,
        volume=12.0,
    )
    events: list[str] = []

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)

    class FailingDb:
        def execute(self, _stmt, _params=None):
            raise OperationalError(
                "SELECT",
                {},
                Exception('materialized view "candles_1h" has not been populated'),
            )

    assert _fetch_view_candle_points(FailingDb(), 1, 60, 1) == []
    assert _fetch_view_candle_points_between(FailingDb(), 1, 60, point.timestamp, point.timestamp) == []
    assert aggregate_has_rows(FailingDb(), 1, 60) is False

    class RefreshConnection:
        def execution_options(self, **kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _stmt, _params):
            raise ProgrammingError(
                "CALL",
                {},
                Exception("procedure refresh_continuous_aggregate does not exist"),
            )

    class RefreshBind:
        def connect(self):
            return RefreshConnection()

    class RefreshDb:
        def get_bind(self):
            return RefreshBind()

    refresh_continuous_aggregate_range(RefreshDb(), 60, point.timestamp, point.timestamp)

    assert "aggregate.view_read.fallback" in events
    assert "aggregate.view_range_read.fallback" in events
    assert "aggregate.has_rows.fallback" in events
    assert "aggregate.refresh.skipped" in events
