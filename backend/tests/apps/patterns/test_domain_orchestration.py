from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from src.apps.cross_market.models import Sector
from src.apps.cross_market.models import SectorMetric
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.models import Coin
from src.apps.patterns.domain.base import PatternDetection, PatternDetector
from src.apps.patterns.domain.clusters import build_pattern_clusters
from src.apps.patterns.domain.cycle import _detect_cycle_phase, refresh_market_cycles, update_market_cycle
from src.apps.patterns.domain.discovery import _window_signature, refresh_discovered_patterns
from src.apps.patterns.domain.engine import PatternEngine
from src.apps.patterns.domain.hierarchy import build_hierarchy_signals
from src.apps.patterns.domain.narrative import _capital_wave_bucket, _coin_bar_return, build_sector_narratives, refresh_sector_metrics
from src.apps.patterns.domain.registry import sync_pattern_metadata
from src.apps.patterns.domain.utils import signal_timestamp
from src.apps.patterns.models import PatternFeature
from src.apps.signals.models import Signal
from tests.factories.market_data import build_candle_points
from tests.cross_market_support import DEFAULT_START, seed_candles
from tests.fusion_support import create_test_coin, insert_signals


class _StaticBullishDetector(PatternDetector):
    slug = "bull_flag"
    category = "continuation"

    def detect(self, candles, indicators):
        del indicators
        return [
            PatternDetection(
                slug=self.slug,
                signal_type="pattern_bull_flag",
                confidence=0.83,
                candle_timestamp=signal_timestamp(candles),
                category=self.category,
            )
        ]


def test_cluster_and_hierarchy_domains_build_real_meta_signals(db_session, seeded_api_state) -> None:
    sync_pattern_metadata(db_session)
    timestamp = seeded_api_state["signal_timestamp"]
    btc = seeded_api_state["btc"]
    eth = seeded_api_state["eth"]

    btc_metrics = db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(btc.id)))
    assert btc_metrics is not None
    btc_metrics.trend_score = 72
    btc_metrics.price_current = 100.0
    btc_metrics.volatility = 0.8

    insert_signals(
        db_session,
        coin_id=int(btc.id),
        timeframe=15,
        candle_timestamp=timestamp,
        items=[
            ("pattern_breakout_retest", 0.81),
            ("pattern_volume_spike", 0.88),
        ],
    )
    cluster_result = build_pattern_clusters(db_session, coin_id=int(btc.id), timeframe=15, candle_timestamp=timestamp)
    assert cluster_result["status"] == "ok"
    assert cluster_result["created"] != 0
    assert db_session.scalar(
        select(Signal).where(
            Signal.coin_id == int(btc.id),
            Signal.timeframe == 15,
            Signal.candle_timestamp == timestamp,
            Signal.signal_type == "pattern_cluster_bullish",
        )
    ) is not None

    hierarchy_result = build_hierarchy_signals(db_session, coin_id=int(btc.id), timeframe=15, candle_timestamp=timestamp)
    hierarchy_signals = {
        row.signal_type
        for row in db_session.scalars(
            select(Signal).where(
                Signal.coin_id == int(btc.id),
                Signal.timeframe == 15,
                Signal.candle_timestamp == timestamp,
                Signal.signal_type.like("pattern_hierarchy_%"),
            )
        ).all()
    }
    assert hierarchy_result["created"] != 0
    assert hierarchy_signals == {"pattern_hierarchy_accumulation", "pattern_hierarchy_trend_continuation"}

    eth_metrics = db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(eth.id)))
    assert eth_metrics is not None
    eth_metrics.trend_score = 32
    eth_metrics.price_current = 100.0
    eth_metrics.volatility = 5.0
    db_session.commit()

    insert_signals(
        db_session,
        coin_id=int(eth.id),
        timeframe=60,
        candle_timestamp=timestamp,
        items=[
            ("pattern_bear_flag", 0.82),
            ("pattern_rising_channel_breakdown", 0.8),
            ("pattern_volume_climax", 0.9),
            ("pattern_momentum_exhaustion", 0.86),
        ],
    )
    bearish_cluster = build_pattern_clusters(db_session, coin_id=int(eth.id), timeframe=60, candle_timestamp=timestamp)
    assert bearish_cluster["status"] == "ok"
    assert bearish_cluster["created"] != 0
    bearish_hierarchy = build_hierarchy_signals(db_session, coin_id=int(eth.id), timeframe=60, candle_timestamp=timestamp)
    bearish_signals = {
        row.signal_type
        for row in db_session.scalars(
            select(Signal).where(
                Signal.coin_id == int(eth.id),
                Signal.timeframe == 60,
                Signal.candle_timestamp == timestamp,
                Signal.signal_type.like("pattern_hierarchy_%"),
            )
        ).all()
    }
    assert bearish_hierarchy["created"] != 0
    assert bearish_signals == {"pattern_hierarchy_distribution", "pattern_hierarchy_trend_exhaustion"}

    pattern_hierarchy_feature = db_session.get(PatternFeature, "pattern_hierarchy")
    pattern_clusters_feature = db_session.get(PatternFeature, "pattern_clusters")
    assert pattern_hierarchy_feature is not None and pattern_clusters_feature is not None
    pattern_hierarchy_feature.enabled = False
    pattern_clusters_feature.enabled = False
    db_session.commit()
    assert build_hierarchy_signals(db_session, coin_id=int(btc.id), timeframe=15, candle_timestamp=timestamp)["reason"] == "pattern_hierarchy_disabled"
    assert build_pattern_clusters(db_session, coin_id=int(btc.id), timeframe=15, candle_timestamp=timestamp)["reason"] == "pattern_clusters_disabled"


def test_cycle_discovery_and_narrative_domains_cover_real_market_state(db_session, seeded_market, seeded_api_state, monkeypatch) -> None:
    sync_pattern_metadata(db_session)
    btc = seeded_api_state["btc"]
    timestamp = seeded_api_state["signal_timestamp"]

    assert _detect_cycle_phase(trend_score=10, regime="high_volatility", volatility=8.0, price_current=100.0, pattern_density=0, cluster_frequency=0, sector_strength=None, capital_flow=None)[0] == "CAPITULATION"
    assert _detect_cycle_phase(trend_score=50, regime="sideways_range", volatility=1.0, price_current=100.0, pattern_density=0, cluster_frequency=0, sector_strength=None, capital_flow=0.0)[0] == "ACCUMULATION"
    assert _detect_cycle_phase(trend_score=75, regime="bull_trend", volatility=1.0, price_current=100.0, pattern_density=3, cluster_frequency=1, sector_strength=0.3, capital_flow=0.1)[0] == "MARKUP"
    assert _detect_cycle_phase(trend_score=75, regime="bull_trend", volatility=5.0, price_current=100.0, pattern_density=0, cluster_frequency=0, sector_strength=0.3, capital_flow=0.1)[0] == "LATE_MARKUP"
    assert _detect_cycle_phase(trend_score=30, regime="bear_trend", volatility=3.0, price_current=100.0, pattern_density=1, cluster_frequency=1, sector_strength=-0.2, capital_flow=-0.1)[0] == "MARKDOWN"
    assert _detect_cycle_phase(trend_score=52, regime="sideways_range", volatility=3.5, price_current=100.0, pattern_density=1, cluster_frequency=0, sector_strength=0.0, capital_flow=-0.1)[0] == "DISTRIBUTION"
    assert _detect_cycle_phase(trend_score=55, regime="unknown", volatility=1.0, price_current=100.0, pattern_density=0, cluster_frequency=0, sector_strength=0.0, capital_flow=0.0)[0] == "ACCUMULATION"

    missing_coin = create_test_coin(db_session, symbol="MISSING_EVT", name="Missing Metrics")
    missing_metrics = db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(missing_coin.id)))
    if missing_metrics is not None:
        db_session.delete(missing_metrics)
        db_session.commit()
    assert update_market_cycle(db_session, coin_id=int(missing_coin.id), timeframe=15)["reason"] == "coin_metrics_not_found"

    btc_metrics = db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(btc.id)))
    assert btc_metrics is not None
    btc_metrics.trend_score = 78
    btc_metrics.price_current = 100.0
    btc_metrics.volatility = 1.2
    cycle_timestamp = timestamp + timedelta(minutes=15)
    db_session.add(
        SectorMetric(
            sector_id=int(btc.sector_id),
            timeframe=15,
            sector_strength=0.91,
            relative_strength=0.83,
            capital_flow=0.62,
            avg_price_change_24h=5.4,
            avg_volume_change_24h=17.0,
            volatility=0.052,
            trend="up",
            updated_at=timestamp,
        )
    )
    insert_signals(
        db_session,
        coin_id=int(btc.id),
        timeframe=15,
        candle_timestamp=cycle_timestamp,
        items=[
            ("pattern_breakout_retest", 0.8),
            ("pattern_cluster_bullish", 0.88),
        ],
    )
    db_session.commit()

    updated_cycle = update_market_cycle(db_session, coin_id=int(btc.id), timeframe=15)
    assert updated_cycle["status"] == "ok"
    assert updated_cycle["cycle_phase"] == "MARKUP"

    cycle_refresh = refresh_market_cycles(db_session)
    assert cycle_refresh["status"] == "ok"
    assert cycle_refresh["cycles"] >= 4

    discovery_feature = db_session.get(PatternFeature, "pattern_discovery_engine")
    assert discovery_feature is not None
    discovery_feature.enabled = False
    db_session.commit()
    assert refresh_discovered_patterns(db_session)["reason"] == "pattern_discovery_disabled"
    discovery_feature.enabled = True
    db_session.commit()
    signature = _window_signature([100.0 + index * 0.5 for index in range(24)])
    assert signature == _window_signature([100.0 + index * 0.5 for index in range(24)])
    repeating_candles = build_candle_points(
        closes=([100.0, 101.0, 100.5, 101.5] * 20),
        volumes=[1000.0] * 80,
    )
    sparse_coin = create_test_coin(db_session, symbol="DSHORT_EVT", name="Discovery Short")
    sparse_coin.candles_config = [{"interval": "1h", "retention_bars": 36}]
    invalid_interval_coin = create_test_coin(db_session, symbol="DINVAL_EVT", name="Discovery Invalid")
    invalid_interval_coin.candles_config = [{"interval": "10m", "retention_bars": 48}]
    db_session.commit()
    sparse_candles = build_candle_points(
        closes=([100.0, 100.6, 100.2, 100.8] * 9),
        volumes=[900.0] * 36,
        timeframe_minutes=60,
    )
    monkeypatch.setattr(
        "src.apps.patterns.domain.discovery.fetch_candle_points",
        lambda db, coin_id, timeframe, limit: (
            sparse_candles
            if coin_id == int(sparse_coin.id) and timeframe == 60
            else repeating_candles
            if timeframe == 15
            else []
        ),
    )
    discovery_result = refresh_discovered_patterns(db_session)
    assert discovery_result["status"] == "ok"
    assert discovery_result["patterns"] > 0

    monkeypatch.setattr("src.apps.patterns.domain.discovery.fetch_candle_points", lambda db, coin_id, timeframe, limit: [])
    empty_discovery = refresh_discovered_patterns(db_session)
    assert empty_discovery == {"status": "ok", "patterns": 0}

    refresh_result = refresh_sector_metrics(db_session, timeframe=15)
    assert refresh_result["status"] == "ok"
    assert refresh_result["updated"] != 0
    coin_bar_return = _coin_bar_return(db_session, int(btc.id), 15)
    assert coin_bar_return[0] is not None
    assert coin_bar_return[1] is not None
    assert _capital_wave_bucket(btc, btc_metrics, top_sector_id=int(btc.sector_id)) in {"large_caps", "sector_leaders", "btc"}

    narratives = build_sector_narratives(db_session)
    assert narratives
    assert any(item.timeframe == 15 for item in narratives)


def test_pattern_engine_covers_incremental_bootstrap_and_history_paths(db_session, seeded_market, monkeypatch) -> None:
    engine = PatternEngine()
    coin_id = int(seeded_market["BTCUSD_EVT"]["coin_id"])
    candles = build_candle_points(closes=[100.0 + 0.5 * index for index in range(40)], volumes=[1000.0] * 40)

    monkeypatch.setattr("src.apps.patterns.domain.engine.feature_enabled", lambda db, slug: False)
    assert engine.detect_incremental(db_session, coin_id=coin_id, timeframe=15)["reason"] == "pattern_detection_disabled"

    monkeypatch.setattr("src.apps.patterns.domain.engine.feature_enabled", lambda db, slug: True)
    monkeypatch.setattr("src.apps.patterns.domain.engine.fetch_candle_points", lambda db, coin_id, timeframe, lookback: candles[:20])
    assert engine.detect_incremental(db_session, coin_id=coin_id, timeframe=15)["reason"] == "insufficient_candles"

    monkeypatch.setattr("src.apps.patterns.domain.engine.fetch_candle_points", lambda db, coin_id, timeframe, lookback: candles)
    monkeypatch.setattr("src.apps.patterns.domain.engine.load_active_detectors", lambda db, timeframe: [_StaticBullishDetector()])
    monkeypatch.setattr(
        "src.apps.patterns.domain.engine.current_indicator_map",
        lambda candles: {
            "price_current": candles[-1].close,
            "ema_50": candles[-1].close * 0.99,
            "ema_200": candles[-1].close * 0.95,
            "current_volume": candles[-1].volume,
            "average_volume_20": 1000.0,
        },
    )
    monkeypatch.setattr("src.apps.patterns.domain.engine.apply_pattern_context", lambda detection, detector, indicators, regime: detection)
    monkeypatch.setattr("src.apps.patterns.domain.engine.apply_pattern_success_validation", lambda db, detection, timeframe, market_regime, coin_id, emit_events, snapshot_cache: detection)

    result = engine.detect_incremental(db_session, coin_id=coin_id, timeframe=15, regime="bull_trend")
    assert result["status"] == "ok"
    assert result["coin_id"] == coin_id
    assert result["timeframe"] == 15
    assert result["detections"] == 1
    assert result["created"] != 0
    assert db_session.scalar(
        select(Signal).where(
            Signal.coin_id == coin_id,
            Signal.timeframe == 15,
            Signal.signal_type == "pattern_bull_flag",
        )
    ) is not None
    assert engine._coin_has_pattern_history(db_session, coin_id)

    actual_coin = db_session.get(Coin, coin_id)
    assert actual_coin is not None
    skipped = engine.bootstrap_coin(db_session, coin=actual_coin, force=False)
    assert skipped["reason"] == "pattern_history_exists"

    fresh_coin = create_test_coin(db_session, symbol="BOOT_EVT", name="Bootstrap Coin")
    fresh_coin.candles_config = [{"interval": "15m", "retention_bars": 40}]
    db_session.commit()
    created = engine.bootstrap_coin(db_session, coin=fresh_coin, force=True)
    assert created["status"] == "ok"
    assert created["detections"] > 0
    assert created["created"] != 0


def test_cluster_hierarchy_engine_and_narrative_guard_paths(db_session, seeded_api_state, monkeypatch) -> None:
    sync_pattern_metadata(db_session)
    timestamp = seeded_api_state["signal_timestamp"]
    btc = seeded_api_state["btc"]
    sol = seeded_api_state["sol"]

    no_patterns_cluster = build_pattern_clusters(
        db_session,
        coin_id=int(btc.id),
        timeframe=240,
        candle_timestamp=timestamp + timedelta(days=30),
    )
    assert no_patterns_cluster["reason"] == "pattern_signals_not_found"

    no_patterns_hierarchy = build_hierarchy_signals(
        db_session,
        coin_id=int(btc.id),
        timeframe=240,
        candle_timestamp=timestamp + timedelta(days=30),
    )
    assert no_patterns_hierarchy["reason"] == "pattern_signals_not_found"

    engine = PatternEngine()
    candles = build_candle_points(closes=[100.0 + 0.5 * index for index in range(40)], volumes=[1000.0] * 40)
    indicators = {
        "price_current": candles[-1].close,
        "ema_50": candles[-1].close * 0.99,
        "ema_200": candles[-1].close * 0.95,
        "current_volume": candles[-1].volume,
        "average_volume_20": 1000.0,
    }

    class _DisabledDetector(PatternDetector):
        slug = "disabled_detector"
        category = "continuation"
        enabled = False

        def detect(self, candles, indicators):
            del candles, indicators
            return []

    class _NeedsVolumeDetector(PatternDetector):
        slug = "needs_volume"
        category = "continuation"
        required_indicators = ["current_volume", "average_volume_20", "ema_20"]

        def detect(self, candles, indicators):
            del candles, indicators
            return []

    class _PassingDetector(PatternDetector):
        slug = "bull_flag"
        category = "continuation"

        def detect(self, candles, indicators):
            del indicators
            return [
                PatternDetection(
                    slug="bull_flag",
                    signal_type="pattern_bull_flag",
                    confidence=0.82,
                    candle_timestamp=signal_timestamp(candles),
                    category="continuation",
                )
            ]

    monkeypatch.setattr("src.apps.patterns.domain.engine.load_pattern_success_cache", lambda *args, **kwargs: {})
    monkeypatch.setattr("src.apps.patterns.domain.engine.apply_pattern_context", lambda **kwargs: None)
    assert engine.detect(
        db_session,
        coin_id=int(btc.id),
        candles=candles,
        indicators=indicators,
        detectors=[_DisabledDetector(), _NeedsVolumeDetector(), _PassingDetector()],
        timeframe=15,
        regime="bull_trend",
    ) == []

    monkeypatch.setattr(
        "src.apps.patterns.domain.engine.apply_pattern_context",
        lambda detection, detector, indicators, regime: detection,
    )
    monkeypatch.setattr("src.apps.patterns.domain.engine.apply_pattern_success_validation", lambda *args, **kwargs: None)
    assert engine.detect(
        db_session,
        coin_id=int(btc.id),
        candles=candles,
        indicators=indicators,
        detectors=[_PassingDetector()],
        timeframe=15,
        regime="bull_trend",
    ) == []
    assert engine._insert_detections(db_session, coin_id=int(btc.id), timeframe=15, detections=[]) == 0

    monkeypatch.setattr("src.apps.patterns.domain.engine.feature_enabled", lambda db, slug: False)
    assert engine.bootstrap_coin(db_session, coin=btc, force=True)["reason"] == "pattern_detection_disabled"

    bootstrap_coin = create_test_coin(db_session, symbol="BRANCH_EVT", name="Branch Coin")
    bootstrap_coin.candles_config = [
        {"interval": "3m", "retention_bars": 40},
        {"interval": "15m", "retention_bars": 40},
        {"interval": "1h", "retention_bars": 40},
    ]
    db_session.commit()

    monkeypatch.setattr("src.apps.patterns.domain.engine.feature_enabled", lambda db, slug: True)
    monkeypatch.setattr(
        "src.apps.patterns.domain.engine.load_active_detectors",
        lambda db, timeframe: [] if timeframe == 15 else [_PassingDetector()],
    )
    monkeypatch.setattr(
        "src.apps.patterns.domain.engine.fetch_candle_points",
        lambda db, coin_id, timeframe, lookback: candles[:20] if timeframe == 60 else candles,
    )
    guarded_bootstrap = engine.bootstrap_coin(db_session, coin=bootstrap_coin, force=True)
    assert guarded_bootstrap["status"] == "ok"
    assert guarded_bootstrap["detections"] == 0

    assert _capital_wave_bucket(sol, SimpleNamespace(market_cap=2_000_000_000.0), top_sector_id=int(sol.sector_id)) == "sector_leaders"
    btc_dominance_coin = db_session.scalar(select(Coin).where(Coin.symbol == "BTCUSD")) or btc
    metrics_rows = {row.coin_id: row for row in db_session.scalars(select(CoinMetrics)).all()}
    original_metrics = {
        coin_id: (row.market_cap, row.price_change_24h, row.volume_change_24h)
        for coin_id, row in metrics_rows.items()
    }
    orphan_sector = Sector(name="orphan_sector", description="no coins")
    db_session.add(orphan_sector)
    db_session.commit()
    try:
        for metrics in metrics_rows.values():
            metrics.market_cap = 0.0
        refresh_sector_metrics(db_session, timeframe=15)
        narratives = build_sector_narratives(db_session)
        assert narratives and all(item.rotation_state is None for item in narratives)

        monkeypatch.setattr("src.apps.patterns.domain.narrative._coin_bar_return", lambda *args, **kwargs: (None, None))
        assert refresh_sector_metrics(db_session, timeframe=15)["status"] == "ok"
        monkeypatch.undo()

        for row in metrics_rows.values():
            row.market_cap = 1_000_000_000.0
            row.price_change_24h = 1.0
        metrics_rows[int(btc_dominance_coin.id)].market_cap = 20_000_000_000.0
        metrics_rows[int(btc_dominance_coin.id)].price_change_24h = -2.0
        refresh_sector_metrics(db_session, timeframe=15)
        assert any(item.rotation_state == "sector_leadership_change" for item in build_sector_narratives(db_session))

        for row in metrics_rows.values():
            row.market_cap = 1_000_000_000.0
            row.price_change_24h = 1.0
        metrics_rows[int(btc_dominance_coin.id)].market_cap = 20_000_000_000.0
        metrics_rows[int(btc_dominance_coin.id)].price_change_24h = 2.0
        refresh_sector_metrics(db_session, timeframe=15)
        assert any(item.rotation_state == "btc_dominance_rising" for item in build_sector_narratives(db_session))

        for row in metrics_rows.values():
            row.market_cap = 10_000_000_000.0
            row.price_change_24h = 1.0
        metrics_rows[int(btc_dominance_coin.id)].market_cap = 1_000_000.0
        metrics_rows[int(btc_dominance_coin.id)].price_change_24h = -3.0
        refresh_sector_metrics(db_session, timeframe=15)
        assert any(item.rotation_state == "btc_dominance_falling" for item in build_sector_narratives(db_session))
    finally:
        for coin_id, (market_cap, price_change_24h, volume_change_24h) in original_metrics.items():
            metrics_rows[coin_id].market_cap = market_cap
            metrics_rows[coin_id].price_change_24h = price_change_24h
            metrics_rows[coin_id].volume_change_24h = volume_change_24h
        db_session.delete(orphan_sector)
        db_session.commit()
        refresh_sector_metrics(db_session, timeframe=15)


def test_refresh_sector_metrics_skips_when_sectors_missing(db_session, monkeypatch) -> None:
    class _EmptyResult:
        def all(self):
            return []

    monkeypatch.setattr(db_session, "scalars", lambda stmt: _EmptyResult())
    assert refresh_sector_metrics(db_session, timeframe=15)["reason"] == "sectors_not_found"


def test_sync_narratives_handle_missing_metric_snapshots_and_empty_capital_wave(
    db_session,
    seeded_api_state,
    monkeypatch,
) -> None:
    sol = seeded_api_state["sol"]
    delayed_metrics_coin = create_test_coin(db_session, symbol="AALTMISS_EVT", name="Delayed Metrics Coin")
    delayed_metrics_coin.sector_id = int(sol.sector_id)
    delayed_metrics_coin.sector_code = sol.sector_code
    db_session.commit()
    seed_candles(
        db_session,
        coin=delayed_metrics_coin,
        interval="15m",
        closes=[22.0 + (index * 0.25) for index in range(30)],
        start=DEFAULT_START,
    )
    delayed_metrics_row = db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(delayed_metrics_coin.id)))
    assert delayed_metrics_row is not None
    db_session.delete(delayed_metrics_row)
    db_session.commit()

    refresh_result = refresh_sector_metrics(db_session, timeframe=15)
    assert refresh_result["status"] == "ok"

    sector_metric = db_session.get(SectorMetric, (int(sol.sector_id), 15))
    assert sector_metric is not None
    assert float(sector_metric.sector_strength) != 0.0

    monkeypatch.setattr("src.apps.patterns.domain.narrative._coin_bar_return", lambda *args, **kwargs: (None, None))
    narratives = build_sector_narratives(db_session)
    assert narratives
    assert all(item.capital_wave is None for item in narratives)
