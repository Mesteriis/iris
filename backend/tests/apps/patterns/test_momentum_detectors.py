from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import importlib

from src.apps.market_data.candles import CandlePoint

momentum = importlib.import_module("src.apps.patterns.domain.detectors.momentum")


def _candles(count: int, *, start_price: float = 100.0) -> list[CandlePoint]:
    base = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    candles: list[CandlePoint] = []
    price = start_price
    for index in range(count):
        candles.append(
            CandlePoint(
                timestamp=base + timedelta(minutes=15 * index),
                open=price,
                high=price + 1.0,
                low=price - 1.0,
                close=price + 0.5,
                volume=100.0 + index,
            )
        )
        price += 1.0
    return candles


def test_momentum_detectors_short_inputs_return_empty() -> None:
    short = _candles(10)
    for detector in momentum.build_momentum_detectors():
        assert detector.detect(short, {}) == []


def test_rsi_and_macd_divergence_detectors(monkeypatch) -> None:
    candles = _candles(80)
    prices = [100.0 + index for index in range(80)]
    prices[-2], prices[-1] = 120.0, 121.0
    rsi_values = [50.0] * 80
    rsi_values[10], rsi_values[20] = 30.0, 45.0
    histogram = [0.0] * 80
    histogram[10], histogram[20] = -2.0, -0.5

    monkeypatch.setattr(momentum, "closes", lambda _candles: prices)
    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: rsi_values)
    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.0] * 80, [0.0] * 80, histogram))
    monkeypatch.setattr(
        momentum,
        "find_pivots",
        lambda _prices, kind: [SimpleNamespace(index=10, price=95.0), SimpleNamespace(index=20, price=90.0)]
        if kind == "low"
        else [SimpleNamespace(index=10, price=100.0)],
    )

    assert momentum.RsiDivergenceDetector().detect(candles, {})[0].slug == "rsi_divergence"
    assert momentum.MacdDivergenceDetector().detect(candles, {})[0].slug == "macd_divergence"

    prices[-2], prices[-1] = 121.0, 120.0
    rsi_values[10], rsi_values[20] = 70.0, 55.0
    histogram[10], histogram[20] = 2.0, 0.5
    monkeypatch.setattr(
        momentum,
        "find_pivots",
        lambda _prices, kind: [SimpleNamespace(index=10, price=90.0)]
        if kind == "low"
        else [SimpleNamespace(index=10, price=105.0), SimpleNamespace(index=20, price=115.0)],
    )

    assert momentum.RsiDivergenceDetector().detect(candles, {})[0].slug == "rsi_divergence"
    assert momentum.MacdDivergenceDetector().detect(candles, {})[0].slug == "macd_divergence"


def test_divergence_detectors_wait_for_confirmed_high_pivots(monkeypatch) -> None:
    candles = _candles(80)
    prices = [100.0 + (index * 0.2) for index in range(80)]
    rsi_values = [50.0] * 80
    histogram = [0.0] * 80
    rsi_values[10], rsi_values[20] = 41.0, 44.0
    histogram[10], histogram[20] = -1.2, -1.0

    monkeypatch.setattr(momentum, "closes", lambda _candles: prices)
    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: rsi_values)
    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.0] * 80, [0.0] * 80, histogram))
    monkeypatch.setattr(
        momentum,
        "find_pivots",
        lambda _prices, kind: [SimpleNamespace(index=10, price=95.0), SimpleNamespace(index=20, price=96.0)]
        if kind == "low"
        else [SimpleNamespace(index=12, price=104.0)],
    )

    assert momentum.RsiDivergenceDetector().detect(candles, {}) == []
    assert momentum.MacdDivergenceDetector().detect(candles, {}) == []


def test_macd_cross_and_momentum_exhaustion(monkeypatch) -> None:
    candles = _candles(60)
    prices = [100.0 + index for index in range(60)]
    rsi_values = [60.0] * 60
    histogram = [0.3] * 60
    histogram[-4:-1] = [0.9, 0.8, 0.7]
    histogram[-1] = 0.4

    monkeypatch.setattr(momentum, "closes", lambda _candles: prices)
    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.1] * 58 + [-0.1, 0.3], [0.2] * 58 + [0.0, 0.2], histogram))
    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: rsi_values)
    monkeypatch.setattr(momentum, "volume_ratio", lambda _candles: 2.0)

    assert momentum.MacdCrossDetector().detect(candles, {})[0].slug == "macd_cross"

    rsi_values[-1] = 80.0
    assert momentum.MomentumExhaustionDetector().detect(candles, {})[0].slug == "momentum_exhaustion"

    rsi_values[-1] = 20.0
    histogram[-4:-1] = [-0.9, -0.8, -0.7]
    histogram[-1] = -0.4
    assert momentum.MomentumExhaustionDetector().detect(candles, {})[0].slug == "momentum_exhaustion"


def test_rsi_threshold_and_failure_swing_detectors(monkeypatch) -> None:
    candles = _candles(60)
    prices = [100.0 + index for index in range(60)]
    rsi_values = [45.0] * 60
    rsi_values[-2], rsi_values[-1] = 49.0, 55.0

    monkeypatch.setattr(momentum, "closes", lambda _candles: prices)
    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: rsi_values)

    assert momentum.RsiThresholdDetector("rsi_reclaim", "bull").detect(candles, {})[0].slug == "rsi_reclaim"

    rsi_values[-2], rsi_values[-1] = 51.0, 45.0
    assert momentum.RsiThresholdDetector("rsi_rejection", "bear").detect(candles, {})[0].slug == "rsi_rejection"

    rsi_values[-8:] = [30.0, 28.0, 32.0, 36.0, 40.0, 45.0, 48.0, 55.0]
    prices[-2], prices[-1] = 119.0, 121.0
    assert momentum.RsiFailureSwingDetector("rsi_failure_swing_bullish", "bull").detect(candles, {})[0].slug == "rsi_failure_swing_bullish"

    rsi_values[-8:] = [70.0, 72.0, 68.0, 64.0, 60.0, 56.0, 52.0, 45.0]
    prices[-2], prices[-1] = 121.0, 119.0
    assert momentum.RsiFailureSwingDetector("rsi_failure_swing_bearish", "bear").detect(candles, {})[0].slug == "rsi_failure_swing_bearish"


def test_macd_zero_cross_and_histogram_impulse(monkeypatch) -> None:
    candles = _candles(60)
    prices = [100.0 + index for index in range(60)]
    macd_line = [0.1] * 58 + [-0.1, 0.3]
    histogram = [0.1, 0.12, 0.14, 0.15, 0.25]

    monkeypatch.setattr(momentum, "closes", lambda _candles: prices)
    monkeypatch.setattr(momentum, "macd_series", lambda _prices: (macd_line, [0.0] * len(macd_line), [0.0] * 55 + histogram))

    assert momentum.MacdZeroCrossDetector("macd_zero_cross_bullish", "bull").detect(candles, {})[0].slug == "macd_zero_cross_bullish"
    assert momentum.MacdHistogramImpulseDetector("macd_histogram_expansion_bullish", "bull").detect(candles, {})[0].slug == "macd_histogram_expansion_bullish"

    macd_line[-2], macd_line[-1] = 0.1, -0.3
    histogram = [-0.1, -0.12, -0.14, -0.15, -0.25]
    monkeypatch.setattr(momentum, "macd_series", lambda _prices: (macd_line, [0.0] * len(macd_line), [0.0] * 55 + histogram))
    assert momentum.MacdZeroCrossDetector("macd_zero_cross_bearish", "bear").detect(candles, {})[0].slug == "macd_zero_cross_bearish"
    assert momentum.MacdHistogramImpulseDetector("macd_histogram_expansion_bearish", "bear").detect(candles, {})[0].slug == "macd_histogram_expansion_bearish"


def test_trend_velocity_detector(monkeypatch) -> None:
    candles = _candles(40)
    prices = [90.0] * 20 + [100.0 + index for index in range(10)] + [111.0 + index * 2 for index in range(10)]
    monkeypatch.setattr(momentum, "closes", lambda _candles: prices)
    assert momentum.TrendVelocityDetector("trend_acceleration", "bull").detect(candles, {})[0].slug == "trend_acceleration"

    prices = [130.0] * 20 + [120.0 - index for index in range(10)] + [109.0 - index * 2 for index in range(10)]
    monkeypatch.setattr(momentum, "closes", lambda _candles: prices)
    assert momentum.TrendVelocityDetector("trend_deceleration", "bear").detect(candles, {})[0].slug == "trend_deceleration"


def test_momentum_detectors_negative_confirmation_paths(monkeypatch) -> None:
    candles = _candles(80)

    monkeypatch.setattr(momentum, "closes", lambda _candles: [100.0 + index for index in range(80)])
    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: [50.0] * 80)
    monkeypatch.setattr(momentum, "find_pivots", lambda _prices, kind: [SimpleNamespace(index=10, price=90.0), SimpleNamespace(index=20, price=91.0)])
    assert momentum.RsiDivergenceDetector().detect(candles, {}) == []

    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.1] * 60, [0.0] * 60, [0.0] * 60))
    assert momentum.MacdCrossDetector().detect(_candles(60), {}) == []
    assert momentum.MacdDivergenceDetector().detect(candles, {}) == []

    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: [60.0] * 60)
    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.0] * 60, [0.0] * 60, [0.2] * 60))
    assert momentum.MomentumExhaustionDetector().detect(_candles(60), {}) == []

    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: [49.0] * 60)
    assert momentum.RsiThresholdDetector("rsi_reclaim", "bull").detect(_candles(60), {}) == []
    assert momentum.RsiFailureSwingDetector("rsi_failure_swing_bullish", "bull").detect(_candles(60), {}) == []

    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.1] * 60, [0.0] * 60, [0.1] * 60))
    assert momentum.MacdZeroCrossDetector("macd_zero_cross_bearish", "bear").detect(_candles(60), {}) == []
    assert momentum.MacdHistogramImpulseDetector("macd_histogram_expansion_bearish", "bear").detect(_candles(60), {}) == []

    monkeypatch.setattr(momentum, "closes", lambda _candles: [100.0] * 40)
    assert momentum.TrendVelocityDetector("trend_acceleration", "bull").detect(_candles(40), {}) == []


def test_momentum_detectors_cover_guard_branches(monkeypatch) -> None:
    candles = _candles(60)

    monkeypatch.setattr(momentum, "closes", lambda _candles: [100.0 + index for index in range(60)])
    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.1] * 34 + [None], [0.0] * 35, [0.0] * 35))
    assert momentum.MacdCrossDetector().detect(candles, {}) == []

    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.1] * 33 + [None, 0.3], [0.0] * 33 + [0.1, 0.2], [0.0] * 35))
    assert momentum.MacdCrossDetector().detect(candles, {}) == []

    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: [50.0] * 59 + [None])
    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.0] * 60, [0.0] * 60, [0.2] * 60))
    assert momentum.MomentumExhaustionDetector().detect(candles, {}) == []

    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: [50.0, 51.0])
    assert momentum.RsiThresholdDetector("rsi_reclaim", "bull").detect(candles, {}) == []

    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: [45.0] * 58 + [None, 55.0])
    assert momentum.RsiThresholdDetector("rsi_reclaim", "bull").detect(candles, {}) == []

    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: [45.0] * 58 + [49.0, 55.0])
    assert momentum.RsiThresholdDetector("rsi_rejection", "bear").detect(candles, {}) == []

    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: [None] * 52 + [30.0, 32.0, 34.0, 36.0, 38.0, None, None, None])
    assert momentum.RsiFailureSwingDetector("rsi_failure_swing_bullish", "bull").detect(candles, {}) == []

    monkeypatch.setattr(momentum, "rsi_series", lambda _prices, _period: [60.0] * 52 + [70.0, 72.0, 68.0, 64.0, 60.0, 56.0, 55.0, 56.0])
    prices = [100.0 + index for index in range(60)]
    prices[-2], prices[-1] = 121.0, 122.0
    monkeypatch.setattr(momentum, "closes", lambda _candles: prices)
    assert momentum.RsiFailureSwingDetector("rsi_failure_swing_bearish", "bear").detect(candles, {}) == []

    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.1] * 34 + [None], [0.0] * 35, [0.0] * 35))
    assert momentum.MacdZeroCrossDetector("macd_zero_cross_bullish", "bull").detect(candles, {}) == []

    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.1] * 35, [0.0] * 35, [0.0] * 35))
    assert momentum.MacdZeroCrossDetector("macd_zero_cross_bullish", "bull").detect(candles, {}) == []

    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.0] * 60, [0.0] * 60, [0.0] * 55 + [0.1, 0.12, 0.13, None, 0.2]))
    assert momentum.MacdHistogramImpulseDetector("macd_histogram_expansion_bullish", "bull").detect(candles, {}) == []

    monkeypatch.setattr(momentum, "macd_series", lambda _prices: ([0.0] * 60, [0.0] * 60, [0.0] * 55 + [0.1, 0.12, 0.14, 0.15, 0.14]))
    assert momentum.MacdHistogramImpulseDetector("macd_histogram_expansion_bullish", "bull").detect(candles, {}) == []

    monkeypatch.setattr(momentum, "closes", lambda _candles: [130.0] * 20 + [120.0 - index for index in range(10)] + [111.0 - index * 0.5 for index in range(10)])
    assert momentum.TrendVelocityDetector("trend_deceleration", "bear").detect(_candles(40), {}) == []
