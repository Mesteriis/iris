from __future__ import annotations

from datetime import datetime, timedelta, timezone

import importlib

from src.apps.market_data.repos import CandlePoint

volatility = importlib.import_module("src.apps.patterns.domain.detectors.volatility")


def _candles(count: int, *, start_price: float = 100.0) -> list[CandlePoint]:
    base = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    candles: list[CandlePoint] = []
    price = start_price
    for index in range(count):
        candles.append(
            CandlePoint(
                timestamp=base + timedelta(minutes=15 * index),
                open=price,
                high=price + 2.0,
                low=price - 2.0,
                close=price + 0.5,
                volume=100.0 + index,
            )
        )
        price += 1.0
    return candles


def test_volatility_detectors_short_inputs_return_empty() -> None:
    short = _candles(10)
    for detector in volatility.build_volatility_detectors():
        assert detector.detect(short, {}) == []


def test_volatility_detectors_success_paths(monkeypatch) -> None:
    candles = _candles(60)
    prices = [100.0 + index for index in range(60)]
    widths = [0.2] * 35 + [0.08] * 24 + [0.03]
    monkeypatch.setattr(volatility, "closes", lambda _candles: prices)
    monkeypatch.setattr(volatility, "volume_ratio", lambda _candles: 2.0)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * len(prices), [100.0] * len(prices), [80.0] * len(prices), widths))
    monkeypatch.setattr(volatility, "atr_series", lambda highs, lows, closes, period: [1.0] * 40 + [2.0] * 19 + [4.0])

    prices[-2], prices[-1] = 100.0, 103.0
    assert volatility.BollingerSqueezeDetector().detect(candles, {})[0].slug == "bollinger_squeeze"

    widths = [0.05] * 50 + [0.1] * 9 + [0.3]
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * len(prices), [100.0] * len(prices), [80.0] * len(prices), widths))
    assert volatility.BollingerExpansionDetector().detect(candles, {})[0].slug == "bollinger_expansion"
    prices[-1] = 200.0
    assert volatility.VolatilityExpansionBreakoutDetector().detect(candles, {})[0].slug == "volatility_expansion_breakout"

    monkeypatch.setattr(volatility, "atr_series", lambda highs, lows, closes, period: [1.0] * 40 + [2.0] * 19 + [4.0])
    assert volatility.AtrSpikeDetector().detect(candles, {})[0].slug == "atr_spike"

    widths = [0.2] * 20 + [0.18] * 10 + [0.05] * 10
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * len(prices), [100.0] * len(prices), [80.0] * len(prices), widths))
    assert volatility.VolatilityCompressionDetector().detect(candles, {})[0].slug == "volatility_compression"

    monkeypatch.setattr(volatility, "atr_series", lambda highs, lows, closes, period: [2.0] * 35 + [0.5] * 15)
    assert volatility.AtrCompressionDetector().detect(candles, {})[0].slug == "atr_compression"

    monkeypatch.setattr(volatility, "atr_series", lambda highs, lows, closes, period: [1.0] * 35 + [2.0] * 5 + [3.0] * 10)
    assert volatility.AtrReleaseDetector().detect(candles, {})[0].slug == "atr_release"

    narrow = _candles(12)
    narrow[-2] = CandlePoint(timestamp=narrow[-2].timestamp, open=100.0, high=100.5, low=100.2, close=100.3, volume=100.0)
    monkeypatch.setattr(volatility, "volume_ratio", lambda _candles: 2.0)
    assert volatility.NarrowRangeBreakoutDetector().detect(narrow, {})[0].slug == "narrow_range_breakout"

    band_prices = [100.0 + index for index in range(40)]
    upper = [price + 1.0 for price in band_prices]
    lower = [price - 1.0 for price in band_prices]
    monkeypatch.setattr(volatility, "closes", lambda _candles: band_prices)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: (upper, [100.0] * len(band_prices), lower, [0.1] * len(band_prices)))
    assert volatility.BandWalkDetector("band_walk_bullish", "bull").detect(_candles(40), {})[0].slug == "band_walk_bullish"

    band_prices = [140.0 - index for index in range(40)]
    upper = [price + 1.0 for price in band_prices]
    lower = [price - 1.0 for price in band_prices]
    monkeypatch.setattr(volatility, "closes", lambda _candles: band_prices)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: (upper, [100.0] * len(band_prices), lower, [0.1] * len(band_prices)))
    assert volatility.BandWalkDetector("band_walk_bearish", "bear").detect(_candles(40), {})[0].slug == "band_walk_bearish"

    snap_prices = [100.0 + index for index in range(40)]
    snap_prices[-2], snap_prices[-1] = 130.0, 99.0
    upper = [110.0] * 40
    lower = [90.0] * 40
    middle = [100.0] * 40
    monkeypatch.setattr(volatility, "closes", lambda _candles: snap_prices)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: (upper, middle, lower, [0.1] * 40))
    assert volatility.MeanReversionSnapDetector().detect(_candles(40), {})[0].slug == "mean_reversion_snap"

    widths = [0.1] * 24 + [0.2] * 10 + [0.35] * 6
    bull_prices = [100.0 + index for index in range(40)]
    bull_prices[-3], bull_prices[-2], bull_prices[-1] = 120.0, 118.0, 121.0
    monkeypatch.setattr(volatility, "closes", lambda _candles: bull_prices)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * 40, [100.0] * 40, [80.0] * 40, widths))
    assert volatility.VolatilityReversalDetector("volatility_reversal_bullish", "bull").detect(_candles(40), {})[0].slug == "volatility_reversal_bullish"

    bear_prices = [140.0 - index for index in range(40)]
    bear_prices[-3], bear_prices[-2], bear_prices[-1] = 120.0, 122.0, 119.0
    monkeypatch.setattr(volatility, "closes", lambda _candles: bear_prices)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * 40, [100.0] * 40, [80.0] * 40, widths))
    assert volatility.VolatilityReversalDetector("volatility_reversal_bearish", "bear").detect(_candles(40), {})[0].slug == "volatility_reversal_bearish"


def test_volatility_detectors_negative_confirmation_paths(monkeypatch) -> None:
    candles = _candles(60)
    prices = [100.0 + index for index in range(60)]

    monkeypatch.setattr(volatility, "closes", lambda _candles: prices)
    monkeypatch.setattr(volatility, "volume_ratio", lambda _candles: 1.0)

    widths = [0.2] * 59 + [None]
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * len(prices), [100.0] * len(prices), [80.0] * len(prices), widths))
    assert volatility.BollingerSqueezeDetector().detect(candles, {}) == []

    widths = [0.03] * 60
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * len(prices), [100.0] * len(prices), [80.0] * len(prices), widths))
    assert volatility.BollingerSqueezeDetector().detect(candles, {}) == []

    widths = [0.2] * 35 + [0.08] * 24 + [0.03]
    prices[-2], prices[-1] = 100.0, 100.5
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * len(prices), [100.0] * len(prices), [80.0] * len(prices), widths))
    assert volatility.BollingerSqueezeDetector().detect(candles, {}) == []

    widths = [0.05] * 59 + [None]
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * len(prices), [100.0] * len(prices), [80.0] * len(prices), widths))
    assert volatility.BollingerExpansionDetector().detect(candles, {}) == []

    widths = [0.05] * 50 + [0.1] * 9 + [0.11]
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * len(prices), [100.0] * len(prices), [80.0] * len(prices), widths))
    assert volatility.BollingerExpansionDetector().detect(candles, {}) == []

    widths = [0.2] * 20 + [0.18] * 10 + [None] * 10
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * len(prices), [100.0] * len(prices), [80.0] * len(prices), widths))
    assert volatility.VolatilityCompressionDetector().detect(candles, {}) == []

    widths = [0.2] * 20 + [0.18] * 10 + [0.16] * 10
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * len(prices), [100.0] * len(prices), [80.0] * len(prices), widths))
    assert volatility.VolatilityCompressionDetector().detect(candles, {}) == []

    widths = [0.05] * 50 + [0.1] * 9 + [0.3]
    prices[-1] = prices[-2]
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * len(prices), [100.0] * len(prices), [80.0] * len(prices), widths))
    assert volatility.VolatilityExpansionBreakoutDetector().detect(candles, {}) == []

    monkeypatch.setattr(volatility, "atr_series", lambda highs, lows, closes, period: [2.0] * 35 + [1.6] * 15)
    assert volatility.AtrCompressionDetector().detect(candles, {}) == []

    too_short = _candles(7)
    monkeypatch.setattr(volatility, "closes", lambda candles: [float(item.close) for item in candles])
    assert volatility.NarrowRangeBreakoutDetector().detect(too_short, {}) == []

    narrow_fail = _candles(12)
    narrow_fail[-2] = CandlePoint(timestamp=narrow_fail[-2].timestamp, open=100.0, high=100.5, low=100.2, close=100.3, volume=100.0)
    narrow_fail[-1] = CandlePoint(timestamp=narrow_fail[-1].timestamp, open=100.3, high=100.4, low=100.2, close=100.31, volume=100.0)
    assert volatility.NarrowRangeBreakoutDetector().detect(narrow_fail, {}) == []

    band_prices = [100.0 + index for index in range(40)]
    upper = [price + 10.0 for price in band_prices]
    lower = [price - 1.0 for price in band_prices]
    monkeypatch.setattr(volatility, "closes", lambda _candles: band_prices)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: (upper, [100.0] * len(band_prices), lower, [0.1] * len(band_prices)))
    assert volatility.BandWalkDetector("band_walk_bullish", "bull").detect(_candles(40), {}) == []

    band_prices = [140.0 - index for index in range(40)]
    upper = [price + 1.0 for price in band_prices]
    lower = [price - 10.0 for price in band_prices]
    monkeypatch.setattr(volatility, "closes", lambda _candles: band_prices)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: (upper, [100.0] * len(band_prices), lower, [0.1] * len(band_prices)))
    assert volatility.BandWalkDetector("band_walk_bearish", "bear").detect(_candles(40), {}) == []

    snap_prices = [100.0 + index for index in range(40)]
    upper = [110.0] * 38 + [None, 110.0]
    lower = [90.0] * 40
    middle = [100.0] * 40
    monkeypatch.setattr(volatility, "closes", lambda _candles: snap_prices)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: (upper, middle, lower, [0.1] * 40))
    assert volatility.MeanReversionSnapDetector().detect(_candles(40), {}) == []

    upper = [110.0] * 40
    lower = [90.0] * 40
    middle = [100.0] * 40
    snap_prices[-2], snap_prices[-1] = 105.0, 104.0
    monkeypatch.setattr(volatility, "closes", lambda _candles: snap_prices)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: (upper, middle, lower, [0.1] * 40))
    assert volatility.MeanReversionSnapDetector().detect(_candles(40), {}) == []

    widths = [0.1] * 24 + [0.2] * 10 + [0.22] * 6
    bull_prices = [100.0 + index for index in range(40)]
    bull_prices[-3], bull_prices[-2], bull_prices[-1] = 120.0, 118.0, 121.0
    monkeypatch.setattr(volatility, "closes", lambda _candles: bull_prices)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * 40, [100.0] * 40, [80.0] * 40, widths))
    assert volatility.VolatilityReversalDetector("volatility_reversal_bullish", "bull").detect(_candles(40), {}) == []

    widths = [0.1] * 24 + [0.2] * 10 + [0.35] * 6
    bull_prices[-3], bull_prices[-2], bull_prices[-1] = 120.0, 121.0, 120.5
    monkeypatch.setattr(volatility, "closes", lambda _candles: bull_prices)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * 40, [100.0] * 40, [80.0] * 40, widths))
    assert volatility.VolatilityReversalDetector("volatility_reversal_bullish", "bull").detect(_candles(40), {}) == []

    bear_prices = [140.0 - index for index in range(40)]
    bear_prices[-3], bear_prices[-2], bear_prices[-1] = 120.0, 119.0, 119.5
    monkeypatch.setattr(volatility, "closes", lambda _candles: bear_prices)
    monkeypatch.setattr(volatility, "bollinger_bands", lambda _prices, period=20: ([120.0] * 40, [100.0] * 40, [80.0] * 40, widths))
    assert volatility.VolatilityReversalDetector("volatility_reversal_bearish", "bear").detect(_candles(40), {}) == []
