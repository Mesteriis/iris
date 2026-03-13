from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select

from src.apps.patterns import cache
from src.apps.patterns.domain.context import _regime_alignment, _signal_regime, _volatility_alignment
from src.apps.patterns.domain.lifecycle import PatternLifecycleState, lifecycle_allows_detection, resolve_lifecycle_state
from src.apps.patterns.domain.utils import (
    average,
    clamp,
    closes,
    current_indicator_map,
    find_pivots,
    highs,
    infer_timeframe,
    linear_slope,
    lows,
    pct_change,
    signal_timestamp,
    volume_ratio,
    volumes,
    window_range,
    within_tolerance,
)
from src.apps.patterns.models import PatternFeature, PatternRegistry
from tests.factories.market_data import build_candle_points
from tests.patterns_support import seed_pattern_catalog_metadata


def test_cache_client_builders_use_configured_redis_url(monkeypatch, settings) -> None:
    sync_client = object()
    async_client = object()

    cache.get_regime_cache_client.cache_clear()
    cache.get_async_regime_cache_client.cache_clear()

    monkeypatch.setattr(cache.Redis, "from_url", lambda url, decode_responses: (url, decode_responses, sync_client))
    monkeypatch.setattr(cache.AsyncRedis, "from_url", lambda url, decode_responses: (url, decode_responses, async_client))

    assert cache.get_regime_cache_client() == (settings.redis_url, True, sync_client)
    assert cache.get_async_regime_cache_client() == (settings.redis_url, True, async_client)

    cache.get_regime_cache_client.cache_clear()
    cache.get_async_regime_cache_client.cache_clear()


def test_utils_calculate_indicators_and_shapes_with_realistic_candles() -> None:
    close_values = [100.0 + index * 0.45 + ((index % 7) - 3) * 0.12 for index in range(240)]
    volume_values = [1200.0 + (index % 9) * 85 for index in range(239)] + [4200.0]
    candles = build_candle_points(closes=close_values, volumes=volume_values)

    assert clamp(1.5, 0.0, 1.0) == 1.0
    assert pct_change(110.0, 100.0) == 0.1
    assert pct_change(10.0, 0.0) == 0.0
    assert average([]) == 0.0
    assert round(average([1.0, 2.0, 3.0]), 4) == 2.0

    assert closes(candles)[-1] == close_values[-1]
    assert highs(candles)[-1] >= closes(candles)[-1]
    assert lows(candles)[-1] <= closes(candles)[-1]
    assert volumes(candles)[-1] == 4200.0
    assert infer_timeframe(candles[:1]) == 15
    assert infer_timeframe(candles) == 15
    assert signal_timestamp(candles) > candles[-1].timestamp

    assert linear_slope([1.0]) == 0.0
    assert linear_slope([1.0, 2.0, 4.0, 8.0]) > 0.0
    assert linear_slope([8.0, 4.0, 2.0, 1.0]) < 0.0

    assert find_pivots([1.0, 2.0, 3.0], kind="high", span=2) == []
    pivots_high = find_pivots([1.0, 3.0, 7.0, 4.0, 2.0, 6.0, 1.0], kind="high", span=1)
    pivots_low = find_pivots([7.0, 4.0, 1.0, 5.0, 8.0, 3.0, 6.0], kind="low", span=1)
    assert [pivot.index for pivot in pivots_high] == [2, 5]
    assert [pivot.index for pivot in pivots_low] == [2, 5]

    assert within_tolerance(10.0, 10.0, 0.0)
    assert within_tolerance(10.0, 10.25, 0.03)
    assert not within_tolerance(10.0, 10.5, 0.03)
    assert window_range([]) == 0.0
    assert window_range([4.0, 8.0, 5.0]) == 4.0
    assert volume_ratio([]) == 0.0
    assert volume_ratio(build_candle_points(closes=[10.0, 10.0, 10.0], volumes=[0.0, 0.0, 0.0])) == 0.0
    assert volume_ratio(candles[-21:]) > 2.0

    indicators = current_indicator_map(candles)
    assert indicators["price_current"] == close_values[-1]
    assert indicators["ema_20"] is not None
    assert indicators["ema_50"] is not None
    assert indicators["ema_200"] is not None
    assert indicators["rsi_14"] is not None
    assert indicators["macd"] is not None
    assert indicators["macd_signal"] is not None
    assert indicators["macd_histogram"] is not None
    assert indicators["atr_14"] is not None
    assert indicators["bb_width"] is not None
    assert indicators["adx_14"] is not None
    assert indicators["average_volume_20"] is not None
    assert indicators["volume_ratio_20"] is not None


def test_lifecycle_registry_and_context_helpers_with_real_rows(db_session) -> None:
    assert lifecycle_allows_detection(PatternLifecycleState.ACTIVE, True)
    assert lifecycle_allows_detection(PatternLifecycleState.EXPERIMENTAL, True)
    assert not lifecycle_allows_detection(PatternLifecycleState.COOLDOWN, True)
    assert not lifecycle_allows_detection(PatternLifecycleState.DISABLED, True)
    assert not lifecycle_allows_detection(PatternLifecycleState.ACTIVE, False)

    assert resolve_lifecycle_state(0.8, True) == PatternLifecycleState.ACTIVE
    assert resolve_lifecycle_state(0.0, True) == PatternLifecycleState.EXPERIMENTAL
    assert resolve_lifecycle_state(-0.4, True) == PatternLifecycleState.COOLDOWN
    assert resolve_lifecycle_state(-1.2, True) == PatternLifecycleState.DISABLED
    assert resolve_lifecycle_state(1.0, False) == PatternLifecycleState.DISABLED

    assert _regime_alignment("mystery_regime", 1) == 1.0
    assert _volatility_alignment("pattern_bollinger_expansion", SimpleNamespace(bb_width=0.1, volatility=0.04)) == 1.15
    assert _volatility_alignment("pattern_random", SimpleNamespace(bb_width=0.09, volatility=0.02)) == 1.08
    assert _volatility_alignment("pattern_random", None) == 1.0
    assert _signal_regime(None, 15) is None
    metrics = SimpleNamespace(
        coin_id=1,
        market_regime_details={"15": {"regime": "high_volatility", "confidence": 0.8}},
        market_regime="bull_trend",
    )
    assert _signal_regime(metrics, 15) == "high_volatility"
    metrics.market_regime_details = None
    assert _signal_regime(metrics, 15) == "bull_trend"

    seed_pattern_catalog_metadata(db_session)
    features = db_session.scalars(select(PatternFeature)).all()
    registry_rows = db_session.scalars(select(PatternRegistry)).all()
    assert len(features) >= 5
    assert len(registry_rows) >= 50
    assert any(row.feature_slug == "pattern_detection" and row.enabled is True for row in features)
    assert not any(row.feature_slug == "missing_feature" for row in features)

    bull_flag = db_session.get(PatternRegistry, "bull_flag")
    assert bull_flag is not None
    bull_flag.enabled = False
    cooldown_slug = next(row.slug for row in registry_rows if row.slug != "bull_flag")
    cooldown_row = db_session.get(PatternRegistry, cooldown_slug)
    assert cooldown_row is not None
    cooldown_row.lifecycle_state = PatternLifecycleState.COOLDOWN.value
    db_session.commit()

    enabled_slugs = {
        row.slug
        for row in db_session.scalars(select(PatternRegistry)).all()
        if lifecycle_allows_detection(str(row.lifecycle_state), bool(row.enabled))
    }
    assert "bull_flag" not in enabled_slugs
    assert cooldown_slug not in enabled_slugs
