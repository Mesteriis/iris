from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import src.apps.indicators.analytics as analytics
import src.apps.indicators.services as indicator_services
from sqlalchemy import select
from src.apps.indicators.analytics import (
    TimeframeSnapshot,
    _activity_fields,
    _calculate_snapshot,
    _coin_base_timeframe,
    _compute_market_regime,
    _compute_price_change,
    _compute_trend,
    _compute_trend_score,
    _compute_volume_metrics,
    _detect_signals,
    _fetch_market_cap,
    _select_primary_snapshot,
    _series_value_pair,
    _snapshot_completeness,
    determine_affected_timeframes,
)
from src.apps.indicators.models import CoinMetrics, IndicatorCache
from src.apps.indicators.query_services import IndicatorQueryService
from src.apps.indicators.repositories import (
    IndicatorCacheRepository,
    IndicatorMetricsRepository,
    IndicatorSignalRepository,
)
from src.apps.indicators.services import IndicatorAnalyticsService, IndicatorMetricsUpdate
from src.apps.market_data.models import Coin
from src.apps.market_data.candles import CandlePoint
from src.apps.signals.models import Signal
from src.core.db.uow import SessionUnitOfWork

from tests.factories.market_data import build_candle_points


def _snapshot(
    *, timeframe: int = 15, timestamp: datetime | None = None, feature_source: str = "candles", **overrides
) -> TimeframeSnapshot:
    base_timestamp = timestamp or datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
    payload = {
        "timeframe": timeframe,
        "feature_source": feature_source,
        "candle_timestamp": base_timestamp,
        "candle_close_timestamp": base_timestamp + timedelta(minutes=timeframe),
        "price_current": 110.0,
        "ema_20": 108.0,
        "ema_50": 106.0,
        "ema_200": 102.0,
        "sma_50": 107.0,
        "sma_200": 101.0,
        "rsi_14": 60.0,
        "macd": 1.3,
        "macd_signal": 1.0,
        "macd_histogram": 0.3,
        "atr_14": 2.0,
        "prev_atr_14": 1.8,
        "bb_upper": 114.0,
        "bb_middle": 109.0,
        "bb_lower": 104.0,
        "bb_width": 0.06,
        "prev_bb_width": 0.05,
        "adx_14": 28.0,
        "current_volume": 3000.0,
        "average_volume_20": 1000.0,
        "range_high_20": 109.0,
        "range_low_20": 96.0,
        "prev_price_current": 107.0,
        "prev_sma_50": 99.0,
        "prev_sma_200": 100.0,
        "prev_rsi_14": 35.0,
        "prev_macd_histogram": -0.2,
        "prev_ema_20": 105.0,
        "prev_ema_50": 104.0,
    }
    payload.update(overrides)
    return TimeframeSnapshot(**payload)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.mark.asyncio
async def test_indicator_analytics_math_and_signal_helpers(monkeypatch) -> None:
    assert _coin_base_timeframe(SimpleNamespace(candles_config=None)) == analytics.BASE_TIMEFRAME_MINUTES
    assert _coin_base_timeframe(SimpleNamespace(candles_config=[{"interval": "1h"}, {"interval": "15m"}])) == 15

    midnight_source = datetime(2026, 3, 11, 23, 45, tzinfo=UTC)
    assert determine_affected_timeframes(timeframe=15, timestamp=midnight_source) == [15, 60, 240, 1440]
    assert determine_affected_timeframes(timeframe=60, timestamp=datetime(2026, 3, 11, 1, 0, tzinfo=UTC)) == [60]

    assert _series_value_pair([]) == (None, None)
    assert _series_value_pair([4.2]) == (4.2, None)
    assert _series_value_pair([1.0, 2.0, 3.0]) == (3.0, 2.0)

    closes = [100 + index * 1.5 for index in range(32)]
    volumes = [1000 + index * 40 for index in range(32)]
    candles = build_candle_points(closes=closes, volumes=volumes, timeframe_minutes=15)
    snapshot = _calculate_snapshot(candles, 15, feature_source="candles")
    assert snapshot is not None
    assert snapshot.price_current == closes[-1]
    assert snapshot.prev_price_current == closes[-2]
    assert snapshot.average_volume_20 is not None
    assert snapshot.range_high_20 is not None
    assert snapshot.range_low_20 is not None
    assert _calculate_snapshot([], 15, feature_source="candles") is None

    assert _compute_price_change([], timedelta(hours=1)) is None
    assert _compute_price_change(candles[:2], timedelta(days=5)) is None
    assert _compute_price_change(candles, timedelta(minutes=15)) == pytest.approx(closes[-1] - closes[-2])

    hourly_closes = [100 + index for index in range(48)]
    hourly_volumes = [100.0] * 24 + [200.0] * 24
    hourly_candles = build_candle_points(closes=hourly_closes, volumes=hourly_volumes, timeframe_minutes=60)
    volume_24h, volume_change_24h, volatility = _compute_volume_metrics(hourly_candles, 60)
    assert volume_24h == pytest.approx(4800.0)
    assert volume_change_24h == pytest.approx(100.0)
    assert volatility is not None and volatility > 0
    assert _compute_volume_metrics([], 15) == (None, None, None)
    assert _compute_volume_metrics(build_candle_points(closes=[100.0], volumes=[50.0]), 15)[2] is None

    low_info = _snapshot(
        ema_20=None,
        ema_50=None,
        sma_50=None,
        sma_200=None,
        rsi_14=None,
        macd=None,
        macd_signal=None,
        macd_histogram=None,
        atr_14=None,
        bb_width=None,
        adx_14=None,
    )
    high_info = _snapshot(timeframe=60)
    assert _snapshot_completeness(low_info) == 0
    assert _select_primary_snapshot({}) is None
    assert _select_primary_snapshot({15: low_info, 60: high_info}) == high_info

    assert _compute_trend(_snapshot()) == "bullish"
    assert _compute_trend(_snapshot(price_current=90.0)) == "bearish"
    assert _compute_trend(_snapshot(sma_200=None)) == "sideways"
    assert _compute_trend(_snapshot(price_current=101.0, sma_200=101.0, ema_50=102.0, macd_histogram=0.2)) == "sideways"

    assert _compute_trend_score(_snapshot(), 15.0) == 100
    bearish_score = _compute_trend_score(
        _snapshot(
            ema_20=90.0,
            ema_50=100.0,
            price_current=90.0,
            sma_200=100.0,
            macd_histogram=-0.5,
            rsi_14=30.0,
            adx_14=10.0,
        ),
        -20.0,
    )
    assert bearish_score == 0
    assert (
        _compute_trend_score(
            _snapshot(
                ema_20=None,
                price_current=None,
                macd_histogram=None,
                rsi_14=None,
                adx_14=None,
            ),
            None,
        )
        == 50
    )
    neutral_score = _compute_trend_score(
        _snapshot(
            rsi_14=50.0,
            adx_14=20.0,
            macd_histogram=0.3,
        ),
        0.0,
    )
    assert 0 <= neutral_score <= 100

    monkeypatch.setattr(analytics, "calculate_activity_score", lambda **kwargs: 88.8)
    monkeypatch.setattr(analytics, "assign_activity_bucket", lambda score: "HOT")
    monkeypatch.setattr(analytics, "analysis_priority_for_bucket", lambda bucket: 1)
    assert _activity_fields(price_change_24h=5.0, volatility=0.2, volume_change_24h=10.0, price_current=100.0) == (
        88.8,
        "HOT",
        1,
    )

    assert _compute_market_regime(_snapshot(sma_200=None), "sideways", 0.0) is None
    assert _compute_market_regime(_snapshot(), "bullish", 20.0) == "bull_market"
    assert _compute_market_regime(_snapshot(price_current=90.0, macd=-1.0), "bearish", -15.0) == "bear_market"
    assert (
        _compute_market_regime(_snapshot(price_current=102.0, sma_200=101.0, macd=0.0, bb_width=0.05), "sideways", 2.0)
        == "accumulation"
    )
    assert (
        _compute_market_regime(_snapshot(price_current=102.0, sma_200=101.0, macd=0.0, bb_width=0.1), "sideways", -5.0)
        == "distribution"
    )
    assert (
        _compute_market_regime(_snapshot(price_current=102.0, sma_200=101.0, macd=0.0), "bullish", 0.0)
        == "accumulation"
    )

    bullish_signals = _detect_signals(_snapshot(rsi_14=25.0))
    assert {item["signal_type"] for item in bullish_signals} == {
        "golden_cross",
        "bullish_breakout",
        "trend_reversal",
        "volume_spike",
        "rsi_oversold",
    }
    bearish_signals = _detect_signals(
        _snapshot(
            prev_sma_50=101.0,
            prev_sma_200=100.0,
            sma_50=99.0,
            sma_200=100.0,
            price_current=90.0,
            range_low_20=95.0,
            prev_macd_histogram=0.3,
            macd_histogram=-0.4,
            prev_rsi_14=69.0,
            rsi_14=75.0,
        )
    )
    assert {item["signal_type"] for item in bearish_signals} == {
        "death_cross",
        "bearish_breakdown",
        "trend_reversal",
        "volume_spike",
        "rsi_overbought",
    }
    assert (
        _detect_signals(
            _snapshot(
                prev_sma_50=None,
                prev_sma_200=None,
                range_high_20=120.0,
                range_low_20=90.0,
                current_volume=None,
                average_volume_20=None,
                prev_macd_histogram=None,
                macd_histogram=None,
                prev_rsi_14=None,
                rsi_14=None,
            )
        )
        == []
    )

    monkeypatch.setattr(analytics.httpx, "AsyncClient", lambda **kwargs: _FakeAsyncClient())

    async def _response(*args, **kwargs):
        del args, kwargs
        return _FakeResponse([{"market_cap": 321000000.0}])

    monkeypatch.setattr(analytics, "rate_limited_get", _response)
    assert await _fetch_market_cap("BTCUSD") == 321000000.0

    async def _empty_response(*args, **kwargs):
        del args, kwargs
        return _FakeResponse([])

    monkeypatch.setattr(analytics, "rate_limited_get", _empty_response)
    assert await _fetch_market_cap("BTCUSD") is None
    assert await _fetch_market_cap("UNKNOWN_EVT") is None


@pytest.mark.asyncio
async def test_indicator_async_repositories_cover_cache_signal_and_metric_paths(
    async_db_session,
    seeded_api_state,
    seeded_market,
    monkeypatch,
) -> None:
    del seeded_market
    btc = await async_db_session.scalar(select(Coin).where(Coin.symbol == "BTCUSD_EVT").limit(1))
    sol = seeded_api_state["sol"]
    assert btc is not None
    btc_id = int(btc.id)
    sol_id = int(sol.id)

    metrics_repo = IndicatorMetricsRepository(async_db_session)
    cache_repo = IndicatorCacheRepository(async_db_session)
    signals_repo = IndicatorSignalRepository(async_db_session)

    seeded_signal_types = await IndicatorSignalRepository(async_db_session).list_types_at_timestamp(
        coin_id=btc_id,
        timeframe=15,
        candle_timestamp=seeded_api_state["signal_timestamp"],
    )
    assert seeded_signal_types
    assert any(signal_type.startswith("pattern_") for signal_type in seeded_signal_types)

    await metrics_repo.delete_by_coin_id(sol_id)
    await async_db_session.commit()
    assert await async_db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == sol_id)) is None

    await metrics_repo.ensure_row(sol_id)
    await async_db_session.commit()
    assert await async_db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == sol_id)) is not None

    timestamp = seeded_api_state["signal_timestamp"] + timedelta(hours=6)
    base_snapshot = _snapshot(timeframe=15, timestamp=timestamp, feature_source="candles")
    aggregate_snapshot = _snapshot(timeframe=60, timestamp=timestamp, feature_source="candles_1h")

    await cache_repo.upsert_snapshots(coin_id=btc_id, snapshots=[], volume_24h=1.0, volume_change_24h=2.0)
    await cache_repo.upsert_snapshots(
        coin_id=btc_id,
        snapshots=[base_snapshot, aggregate_snapshot],
        volume_24h=5000.0,
        volume_change_24h=12.5,
    )
    await async_db_session.commit()
    volume_row = await async_db_session.scalar(
        select(IndicatorCache)
        .where(
            IndicatorCache.coin_id == btc_id,
            IndicatorCache.timeframe == 15,
            IndicatorCache.indicator == "volume_24h",
            IndicatorCache.timestamp == timestamp,
        )
        .limit(1)
    )
    assert volume_row is not None
    assert float(volume_row.value) == 5000.0

    updated_snapshot = replace(base_snapshot, feature_source="recomputed", price_current=222.0)
    await cache_repo.upsert_snapshots(
        coin_id=btc_id,
        snapshots=[updated_snapshot],
        volume_24h=7000.0,
        volume_change_24h=22.5,
    )
    await async_db_session.commit()
    updated_row = await async_db_session.scalar(
        select(IndicatorCache)
        .where(
            IndicatorCache.coin_id == btc_id,
            IndicatorCache.timeframe == 15,
            IndicatorCache.indicator == "price_current",
            IndicatorCache.timestamp == timestamp,
        )
        .limit(1)
    )
    assert updated_row is not None
    assert float(updated_row.value) == 222.0
    assert updated_row.feature_source == "recomputed"

    await signals_repo.insert_known_signals(coin_id=btc_id, timeframe=15, signals=[])
    await signals_repo.insert_known_signals(
        coin_id=btc_id,
        timeframe=15,
        signals=[
            {"signal_type": "golden_cross", "confidence": 0.91, "candle_timestamp": timestamp},
            {"signal_type": "unknown_signal", "confidence": 0.50, "candle_timestamp": timestamp},
        ],
    )
    await signals_repo.insert_known_signals(
        coin_id=btc_id,
        timeframe=15,
        signals=[{"signal_type": "golden_cross", "confidence": 0.91, "candle_timestamp": timestamp}],
    )
    await async_db_session.commit()
    assert await signals_repo.list_types_at_timestamp(
        coin_id=btc_id,
        timeframe=15,
        candle_timestamp=timestamp,
    ) >= {"golden_cross"}

    filtered_signals = await IndicatorQueryService(async_db_session).list_signals(
        symbol="BTCUSD_EVT", timeframe=15, limit=200
    )
    assert any(row.signal_type == "golden_cross" for row in filtered_signals)
    assert await IndicatorQueryService(async_db_session).list_signals(symbol="BTCUSD_EVT", limit=1)
    assert await IndicatorQueryService(async_db_session).list_signals(timeframe=15, limit=1)

    metrics_rows = await IndicatorQueryService(async_db_session).list_coin_metrics()
    assert any(row.symbol == "BTCUSD_EVT" for row in metrics_rows)

    async with SessionUnitOfWork(async_db_session) as uow:
        service = IndicatorAnalyticsService(uow)
        sol_current = await uow.session.get(Coin, sol_id)
        assert sol_current is not None
        minimal_payload = await service._upsert_coin_metrics(
            coin=sol_current,
            base_timeframe=15,
            primary=None,
            base_snapshot=None,
            base_candles=[],
            volume_24h=None,
            volume_change_24h=None,
            volatility=None,
            refresh_market_cap=False,
            market_regime="sideways_range",
            market_regime_details={"15": {"regime": "sideways_range"}},
        )
    assert minimal_payload.coin_id == sol_id
    assert minimal_payload.market_regime == "sideways_range"

    base_candles = build_candle_points(
        closes=[100 + index for index in range(80)],
        volumes=[1000 + (index * 10) for index in range(80)],
        timeframe_minutes=15,
        start=timestamp - timedelta(minutes=15 * 79),
    )
    monkeypatch.setattr(
        indicator_services, "_fetch_market_cap", lambda symbol: __import__("asyncio").sleep(0, result=987654321.0)
    )
    monkeypatch.setattr(indicator_services, "utc_now", lambda: timestamp + timedelta(minutes=1))

    async with SessionUnitOfWork(async_db_session) as uow:
        service = IndicatorAnalyticsService(uow)
        btc_current = await uow.session.get(Coin, btc_id)
        assert btc_current is not None
        full_payload = await service._upsert_coin_metrics(
            coin=btc_current,
            base_timeframe=15,
            primary=_snapshot(timeframe=60, timestamp=timestamp, price_current=210.0, feature_source="candles_1h"),
            base_snapshot=_snapshot(timeframe=15, timestamp=timestamp, price_current=205.0),
            base_candles=base_candles,
            volume_24h=8000.0,
            volume_change_24h=14.0,
            volatility=4.5,
            refresh_market_cap=True,
            market_regime=None,
            market_regime_details={"15": {"regime": "bull_trend", "confidence": 0.81}},
        )
        await uow.commit()
    assert full_payload.market_regime == "bull_market"
    refreshed_metrics = await async_db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == btc_id).limit(1))
    assert refreshed_metrics is not None
    assert float(refreshed_metrics.price_current) == 205.0
    assert float(refreshed_metrics.market_cap) == 987654321.0


@pytest.mark.asyncio
async def test_process_indicator_event_orchestrates_affected_timeframes_and_signal_diff(
    async_db_session,
    seeded_api_state,
    monkeypatch,
) -> None:
    btc = seeded_api_state["btc"]
    base_timestamp = seeded_api_state["signal_timestamp"]
    snapshot_map = {
        15: _snapshot(timeframe=15, timestamp=base_timestamp, feature_source="candles"),
        60: _snapshot(timeframe=60, timestamp=base_timestamp, feature_source="candles_1h"),
        240: _snapshot(timeframe=240, timestamp=base_timestamp, feature_source="candles_4h"),
        1440: _snapshot(timeframe=1440, timestamp=base_timestamp, feature_source="candles_1d"),
    }

    async with SessionUnitOfWork(async_db_session) as uow:
        service = IndicatorAnalyticsService(uow)
        skipped = await service.process_event(coin_id=999999, timeframe=15, timestamp=base_timestamp)
        assert skipped.reason == "coin_not_found"

        range_refreshes: list[tuple[int, datetime, datetime]] = []
        cache_calls: list[tuple[int, list[int], float | None, float | None]] = []
        inserted_signals: list[tuple[int, int, list[dict[str, object]]]] = []
        list_calls: dict[int, int] = {}

        async def _base_bounds(*, coin_id: int):
            assert coin_id == int(btc.id)
            return base_timestamp - timedelta(days=1), base_timestamp

        async def _aggregate_has_rows(*, coin_id: int, timeframe: int):
            del coin_id
            return False

        async def _refresh_range(*, timeframe: int, window_start: datetime, window_end: datetime):
            range_refreshes.append((timeframe, window_start, window_end))

        async def _fetch_points(*, coin_id: int, timeframe: int, limit: int):
            del coin_id, limit
            return [CandlePoint(base_timestamp, 1.0, 1.0, 1.0, 1.0, 1.0)]

        async def _has_direct_candles(*, coin_id: int, timeframe: int):
            del coin_id
            return timeframe == 15

        async def _upsert_metrics(**kwargs):
            del kwargs
            return IndicatorMetricsUpdate(
                coin_id=int(btc.id),
                activity_score=91.0,
                activity_bucket="HOT",
                analysis_priority=1,
                market_regime="fallback_regime",
                price_change_24h=5.0,
                price_change_7d=18.0,
                volatility=4.2,
            )

        async def _cache_upsert(*, coin_id: int, snapshots, volume_24h: float | None, volume_change_24h: float | None):
            cache_calls.append((coin_id, [snapshot.timeframe for snapshot in snapshots], volume_24h, volume_change_24h))

        async def _insert_known_signals(*, coin_id: int, timeframe: int, signals):
            inserted_signals.append((coin_id, timeframe, list(signals)))

        async def _list_signal_types(*, coin_id: int, timeframe: int, candle_timestamp: object):
            del coin_id, candle_timestamp
            count = list_calls.get(timeframe, 0)
            list_calls[timeframe] = count + 1
            return set() if count == 0 else {"existing", "golden_cross", "volume_spike"}

        monkeypatch.setattr(service._candles, "get_base_bounds", _base_bounds)
        monkeypatch.setattr(service._candles, "aggregate_has_rows", _aggregate_has_rows)
        monkeypatch.setattr(service._aggregates, "refresh_range", _refresh_range)
        monkeypatch.setattr(service._candles, "fetch_points", _fetch_points)
        monkeypatch.setattr(service._candles, "has_direct_candles", _has_direct_candles)
        monkeypatch.setattr(service, "_upsert_coin_metrics", _upsert_metrics)
        monkeypatch.setattr(service._cache, "upsert_snapshots", _cache_upsert)
        monkeypatch.setattr(service._signals, "insert_known_signals", _insert_known_signals)
        monkeypatch.setattr(service._signals, "list_types_at_timestamp", _list_signal_types)
        monkeypatch.setattr(indicator_services, "determine_affected_timeframes", lambda **kwargs: [15, 60, 240, 1440])
        monkeypatch.setattr(
            indicator_services,
            "_calculate_snapshot",
            lambda candles, timeframe, feature_source: snapshot_map.get(timeframe),
        )
        monkeypatch.setattr(
            indicator_services, "_compute_volume_metrics", lambda candles, base_timeframe: (6000.0, 12.0, 4.2)
        )
        monkeypatch.setattr(
            indicator_services, "_compute_price_change", lambda candles, delta: 18.0 if delta.days >= 7 else 5.0
        )
        monkeypatch.setattr(indicator_services, "_select_primary_snapshot", lambda snapshots: snapshots[60])
        monkeypatch.setattr(
            service._feature_flags, "is_enabled", lambda feature_slug: __import__("asyncio").sleep(0, result=True)
        )
        monkeypatch.setattr(
            indicator_services,
            "calculate_regime_map",
            lambda snapshots, volatility, price_change_7d: {
                15: SimpleNamespace(regime="bull_trend", confidence=0.81),
                60: SimpleNamespace(regime="bull_trend", confidence=0.84),
            },
        )
        monkeypatch.setattr(indicator_services, "primary_regime", lambda regime_map: "fallback_regime")
        monkeypatch.setattr(
            indicator_services,
            "serialize_regime_map",
            lambda regime_map: {"15": {"regime": "bull_trend", "confidence": 0.81}},
        )
        monkeypatch.setattr(
            indicator_services,
            "_detect_signals",
            lambda snapshot: [
                {
                    "signal_type": "golden_cross",
                    "confidence": 0.91,
                    "candle_timestamp": snapshot.candle_close_timestamp,
                },
                {
                    "signal_type": "volume_spike",
                    "confidence": 0.70,
                    "candle_timestamp": snapshot.candle_close_timestamp,
                },
            ],
        )

        result = await service.process_event(coin_id=int(btc.id), timeframe=15, timestamp=base_timestamp)

    assert result.status == "ok"
    assert result.coin_id == int(btc.id)
    assert result.timeframes == (15, 60, 240, 1440)
    assert len(range_refreshes) == len(indicator_services.AGGREGATE_VIEW_BY_TIMEFRAME) + 3
    assert cache_calls == [(int(btc.id), [15, 60, 240, 1440], 6000.0, 12.0)]
    assert len(inserted_signals) == 4
    assert result.items[0].feature_source == "candles"
    assert result.items[1].feature_source == "candles_1h"
    assert result.items[0].market_regime == "bull_trend"
    assert result.items[2].market_regime == "fallback_regime"
    assert result.items[0].classic_signals == ("golden_cross", "volume_spike")


@pytest.mark.asyncio
async def test_process_indicator_event_covers_missing_bounds_existing_aggregates_and_snapshot_gaps(
    async_db_session,
    seeded_api_state,
    monkeypatch,
) -> None:
    btc = seeded_api_state["btc"]
    base_timestamp = seeded_api_state["signal_timestamp"]

    snapshot_15 = _snapshot(timeframe=15, timestamp=base_timestamp, feature_source="candles")
    snapshot_60 = _snapshot(timeframe=60, timestamp=base_timestamp, feature_source="candles_1h")

    async with SessionUnitOfWork(async_db_session) as uow:
        service = IndicatorAnalyticsService(uow)

        async def _fetch_points(*, coin_id: int, timeframe: int, limit: int):
            del coin_id, timeframe, limit
            return [CandlePoint(base_timestamp, 1.0, 1.0, 1.0, 1.0, 1.0)]

        monkeypatch.setattr(service._candles, "fetch_points", _fetch_points)
        monkeypatch.setattr(
            service._candles,
            "has_direct_candles",
            lambda **kwargs: __import__("asyncio").sleep(0, result=kwargs["timeframe"] == 15),
        )
        monkeypatch.setattr(indicator_services, "determine_affected_timeframes", lambda **kwargs: [15, 60, 240])
        monkeypatch.setattr(
            indicator_services, "_compute_volume_metrics", lambda candles, base_timeframe: (1000.0, 5.0, 1.2)
        )
        monkeypatch.setattr(indicator_services, "_compute_price_change", lambda candles, delta: 3.0)
        monkeypatch.setattr(indicator_services, "_select_primary_snapshot", lambda snapshots: snapshots[15])
        monkeypatch.setattr(
            service._feature_flags, "is_enabled", lambda feature_slug: __import__("asyncio").sleep(0, result=False)
        )
        monkeypatch.setattr(
            service,
            "_upsert_coin_metrics",
            lambda **kwargs: __import__("asyncio").sleep(
                0,
                result=IndicatorMetricsUpdate(
                    coin_id=int(btc.id),
                    activity_score=60.0,
                    activity_bucket="WARM",
                    analysis_priority=2,
                    market_regime="sideways_range",
                    price_change_24h=2.0,
                    price_change_7d=3.0,
                    volatility=1.2,
                ),
            ),
        )
        monkeypatch.setattr(service._cache, "upsert_snapshots", lambda **kwargs: __import__("asyncio").sleep(0))
        monkeypatch.setattr(indicator_services, "_detect_signals", lambda snapshot: [])
        monkeypatch.setattr(service._signals, "insert_known_signals", lambda **kwargs: __import__("asyncio").sleep(0))
        monkeypatch.setattr(
            service._signals, "list_types_at_timestamp", lambda **kwargs: __import__("asyncio").sleep(0, result=set())
        )

        aggregate_refreshes: list[tuple[int, datetime, datetime]] = []
        monkeypatch.setattr(
            service._candles,
            "get_base_bounds",
            lambda **kwargs: __import__("asyncio").sleep(
                0, result=(base_timestamp - timedelta(days=1), base_timestamp)
            ),
        )
        monkeypatch.setattr(
            service._candles, "aggregate_has_rows", lambda **kwargs: __import__("asyncio").sleep(0, result=True)
        )
        monkeypatch.setattr(
            service._aggregates,
            "refresh_range",
            lambda **kwargs: __import__("asyncio").sleep(
                0,
                result=aggregate_refreshes.append((kwargs["timeframe"], kwargs["window_start"], kwargs["window_end"])),
            ),
        )
        monkeypatch.setattr(
            indicator_services,
            "_calculate_snapshot",
            lambda candles, timeframe, feature_source: {15: snapshot_15, 60: snapshot_60, 240: None}.get(timeframe),
        )
        result_with_existing_aggregates = await service.process_event(
            coin_id=int(btc.id),
            timeframe=15,
            timestamp=base_timestamp,
        )
        assert result_with_existing_aggregates.status == "ok"
        assert len(aggregate_refreshes) == 2
        assert [item.timeframe for item in result_with_existing_aggregates.items] == [15, 60]

        monkeypatch.setattr(
            service._candles, "get_base_bounds", lambda **kwargs: __import__("asyncio").sleep(0, result=(None, None))
        )
        monkeypatch.setattr(
            indicator_services,
            "_calculate_snapshot",
            lambda candles, timeframe, feature_source: {15: snapshot_15, 60: None, 240: None}.get(timeframe),
        )
        result_without_bounds = await service.process_event(coin_id=int(btc.id), timeframe=15, timestamp=base_timestamp)

    assert result_without_bounds.status == "ok"
    assert [item.timeframe for item in result_without_bounds.items] == [15]
