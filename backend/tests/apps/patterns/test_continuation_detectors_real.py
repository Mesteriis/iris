from __future__ import annotations

from dataclasses import replace

from src.apps.patterns.domain.detectors.continuation import (
    BaseBreakoutDetector,
    BreakoutRetestDetector,
    ChannelContinuationDetector,
    ConsolidationBreakoutDetector,
    CupAndHandleDetector,
    FlagDetector,
    HandleBreakoutDetector,
    HighTightFlagDetector,
    MeasuredMoveDetector,
    PennantDetector,
    PullbackContinuationDetector,
    SqueezeBreakoutDetector,
    StairStepContinuationDetector,
    TrendPauseBreakoutDetector,
    VolatilityContractionBreakDetector,
    build_continuation_detectors,
)
from tests.factories.market_data import build_candle_points


def test_continuation_detectors_short_inputs_return_empty() -> None:
    short = build_candle_points(closes=[100.0 + index for index in range(10)], volumes=[1000.0] * 10)
    for detector in build_continuation_detectors():
        assert detector.detect(short, {}) == []


def test_continuation_detectors_cover_real_continuation_shapes() -> None:
    bull_flag = build_candle_points(
        closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 112.0, 114.0, 116.0, 118.0, 120.0, 122.0, 124.0, 126.0, 127.0, 128.0, 127.0, 126.0, 125.0, 124.0, 123.0, 122.0, 121.5, 121.0, 120.5, 120.0, 119.5, 119.0, 118.5, 123.0],
        volumes=[1000.0] * 34 + [1600.0],
    )
    assert FlagDetector("bull_flag", "bull").detect(bull_flag, {})[0].slug == "bull_flag"

    bear_flag = build_candle_points(
        closes=[130.0, 129.0, 128.0, 127.0, 126.0, 125.0, 124.0, 123.0, 122.0, 121.0, 120.0, 118.0, 116.0, 114.0, 112.0, 110.0, 108.0, 106.0, 104.0, 103.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 108.5, 109.0, 109.5, 110.0, 110.5, 111.0, 111.5, 106.0],
        volumes=[1000.0] * 34 + [1600.0],
    )
    assert FlagDetector("bear_flag", "bear").detect(bear_flag, {})[0].slug == "bear_flag"

    pennant = build_candle_points(
        closes=[100.0 + index * 1.8 for index in range(20)] + [136.0, 136.2, 136.4, 136.1, 136.0, 135.9, 136.0, 136.1, 136.2, 139.5],
        volumes=[1000.0] * 29 + [1800.0],
    )
    pennant_highs = [138.0, 137.7, 137.4, 137.1, 136.8, 136.5, 136.2, 135.9, 135.6, 140.5]
    pennant_lows = [132.0, 132.3, 132.6, 132.9, 133.2, 133.5, 133.8, 134.1, 134.4, 138.5]
    pennant_closes = [136.0, 136.2, 136.4, 136.1, 136.0, 135.9, 136.0, 136.1, 136.2, 139.5]
    for offset in range(10):
        index = len(pennant) - 10 + offset
        pennant[index] = replace(
            pennant[index],
            open=135.5 if offset == 0 else pennant[index - 1].close,
            high=pennant_highs[offset],
            low=pennant_lows[offset],
            close=pennant_closes[offset],
            volume=1000.0 if offset < 9 else 1800.0,
        )
    assert PennantDetector().detect(pennant, {})[0].slug == "pennant"

    cup_handle = build_candle_points(
        closes=[
            126.0, 125.8, 125.6, 125.4, 125.2, 125.0, 124.8, 124.6, 124.4, 124.2, 124.0, 123.8, 123.6, 123.4, 123.2, 123.0, 122.8, 122.6, 122.4, 122.2,
            121.0, 119.0, 117.0, 115.0, 113.0, 111.0, 109.0, 107.0, 105.0, 103.0, 101.0, 100.0, 101.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 114.0,
            116.0, 118.0, 120.0, 122.0, 123.0, 124.0, 125.0, 126.0, 125.8, 125.6, 125.4, 125.2, 125.0, 124.8, 124.6, 124.8, 125.0, 125.2, 126.0, 127.0,
        ],
        volumes=[1000.0] * 59 + [1500.0],
    )
    assert CupAndHandleDetector().detect(cup_handle, {})[0].slug == "cup_and_handle"

    breakout_retest = build_candle_points(
        closes=[100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 103.0, 103.5, 104.0, 104.5, 105.0, 105.5, 106.0, 106.5, 107.0, 107.5, 108.0, 108.5, 109.0, 109.5, 110.0, 110.5, 111.0, 111.5, 112.0, 114.0, 115.0, 114.5, 113.8, 113.2, 113.0, 113.4, 113.7, 114.2, 114.6, 115.0, 115.2, 115.4, 115.6, 115.8],
        volumes=[1000.0] * 39 + [1500.0],
    )
    assert BreakoutRetestDetector().detect(breakout_retest, {})[0].slug == "breakout_retest"

    consolidation = build_candle_points(closes=[100.0 + 0.1 * index for index in range(23)] + [104.5], volumes=[1000.0] * 23 + [1800.0])
    assert ConsolidationBreakoutDetector().detect(consolidation, {})[0].slug == "consolidation_breakout"

    high_tight = build_candle_points(
        closes=[100.0, 101.0, 102.0, 104.0, 106.0, 108.0, 110.0, 113.0, 116.0, 119.0, 122.0, 125.0, 128.0, 130.0, 132.0, 133.0, 134.0, 135.0, 136.0, 136.5, 137.0, 137.5, 138.0, 138.5, 139.0, 139.3, 139.5, 139.7, 139.8, 139.9, 140.0, 140.5],
        volumes=[1000.0] * 31 + [1700.0],
    )
    assert HighTightFlagDetector().detect(high_tight, {})[0].slug == "high_tight_flag"

    falling_channel = build_candle_points(closes=[130.0 - 0.5 * index for index in range(45)], volumes=[1000.0] * 45)
    channel_highs = [122.0, 121.5, 121.0, 120.5, 120.0, 119.5, 119.0, 118.5, 118.0, 117.5, 117.0, 116.5, 116.0, 115.5, 115.0, 123.5]
    channel_lows = [118.0, 117.5, 117.0, 116.5, 116.0, 115.5, 115.0, 114.5, 114.0, 113.5, 113.0, 112.5, 112.0, 111.5, 111.0, 112.0]
    channel_closes = [119.5, 119.0, 118.5, 118.0, 117.5, 117.0, 116.5, 116.0, 115.5, 115.0, 114.5, 114.0, 113.5, 113.0, 112.5, 123.0]
    for offset in range(16):
        index = len(falling_channel) - 16 + offset
        falling_channel[index] = replace(
            falling_channel[index],
            open=channel_closes[offset - 1] if offset > 0 else 120.0,
            high=channel_highs[offset],
            low=channel_lows[offset],
            close=channel_closes[offset],
            volume=1000.0 if offset < 15 else 1600.0,
        )
    assert ChannelContinuationDetector("falling_channel_breakout", "bull").detect(falling_channel, {})[0].slug == "falling_channel_breakout"

    rising_channel = build_candle_points(closes=[100.0 + 0.5 * index for index in range(45)], volumes=[1000.0] * 45)
    rising_highs = [108.0, 108.5, 109.0, 109.5, 110.0, 110.5, 111.0, 111.5, 112.0, 112.5, 113.0, 113.5, 114.0, 114.5, 115.0, 115.0]
    rising_lows = [104.0, 104.5, 105.0, 105.5, 106.0, 106.5, 107.0, 107.5, 108.0, 108.5, 109.0, 109.5, 110.0, 110.5, 111.0, 102.5]
    rising_closes = [106.0, 106.5, 107.0, 107.5, 108.0, 108.5, 109.0, 109.5, 110.0, 110.5, 111.0, 111.5, 112.0, 112.5, 113.0, 103.0]
    for offset in range(16):
        index = len(rising_channel) - 16 + offset
        rising_channel[index] = replace(
            rising_channel[index],
            open=rising_closes[offset - 1] if offset > 0 else 105.0,
            high=rising_highs[offset],
            low=rising_lows[offset],
            close=rising_closes[offset],
            volume=1000.0 if offset < 15 else 1600.0,
        )
    assert ChannelContinuationDetector("rising_channel_breakdown", "bear").detect(rising_channel, {})[0].slug == "rising_channel_breakdown"

    measured_bull = build_candle_points(
        closes=[96.0, 97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 110.5, 111.0, 110.0, 109.0, 108.0, 107.0, 106.0, 105.5, 105.0, 105.5, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 117.0, 118.0, 119.0, 120.0],
        volumes=[1000.0] * 39 + [1500.0],
    )
    assert MeasuredMoveDetector("measured_move_bullish", "bull").detect(measured_bull, {})[0].slug == "measured_move_bullish"

    measured_bear = build_candle_points(
        closes=[134.0, 133.0, 132.0, 131.0, 130.0, 129.0, 128.0, 127.0, 126.0, 125.0, 124.0, 123.0, 122.0, 121.0, 120.0, 119.5, 119.0, 120.0, 121.0, 122.0, 123.0, 124.0, 124.5, 125.0, 124.5, 124.0, 123.0, 122.0, 121.0, 120.0, 119.0, 118.0, 117.0, 116.0, 115.0, 114.0, 113.0, 112.0, 111.0, 110.0],
        volumes=[1000.0] * 39 + [1500.0],
    )
    assert MeasuredMoveDetector("measured_move_bearish", "bear").detect(measured_bear, {})[0].slug == "measured_move_bearish"

    base_breakout = build_candle_points(
        closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 114.2, 114.4, 114.6, 114.7, 114.8, 114.9, 115.0, 115.1, 115.2, 115.1, 115.0, 114.95, 114.98, 115.05, 115.1, 115.15, 115.2, 115.25, 116.5],
        volumes=[1000.0] * 33 + [1500.0],
    )
    assert BaseBreakoutDetector().detect(base_breakout, {})[0].slug == "base_breakout"

    vcb_bull = build_candle_points(
        closes=[100.0, 102.0, 98.0, 103.0, 97.0, 104.0, 96.0, 105.0, 95.0, 106.0, 94.0, 107.0, 100.0, 101.0, 99.5, 100.5, 100.2, 99.8, 100.3, 100.0, 99.9, 100.1, 100.05, 100.0, 100.1, 100.2, 100.0, 100.1, 100.15, 100.1, 100.12, 100.14, 100.16, 100.18, 100.2, 101.5],
        volumes=[1000.0] * 35 + [1500.0],
    )
    assert VolatilityContractionBreakDetector("volatility_contraction_breakout", "bull").detect(vcb_bull, {})[0].slug == "volatility_contraction_breakout"

    vcb_bear = build_candle_points(
        closes=[120.0, 118.0, 122.0, 117.0, 123.0, 116.0, 124.0, 115.0, 125.0, 114.0, 126.0, 113.0, 120.0, 119.0, 120.5, 119.5, 120.2, 119.8, 120.1, 120.0, 120.05, 119.95, 120.0, 119.98, 120.02, 120.0, 119.99, 120.01, 120.0, 119.98, 119.96, 119.94, 119.92, 119.9, 119.88, 118.0],
        volumes=[1000.0] * 35 + [1500.0],
    )
    assert VolatilityContractionBreakDetector("volatility_contraction_breakdown", "bear").detect(vcb_bear, {})[0].slug == "volatility_contraction_breakdown"

    pullback_bull = build_candle_points(
        closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 117.0, 118.0, 119.0, 120.0, 119.0, 118.0, 117.0, 116.0, 117.0, 118.0, 119.0, 120.0, 121.0],
        volumes=[1000.0] * 29 + [1500.0],
    )
    assert PullbackContinuationDetector("pullback_continuation_bullish", "bull").detect(pullback_bull, {})[0].slug == "pullback_continuation_bullish"

    pullback_bear = build_candle_points(
        closes=[130.0, 129.0, 128.0, 127.0, 126.0, 125.0, 124.0, 123.0, 122.0, 121.0, 120.0, 119.0, 118.0, 117.0, 116.0, 115.0, 114.0, 113.0, 112.0, 111.0, 110.0, 111.0, 112.0, 113.0, 114.0, 113.0, 112.0, 111.0, 110.0, 109.0],
        volumes=[1000.0] * 29 + [1500.0],
    )
    assert PullbackContinuationDetector("pullback_continuation_bearish", "bear").detect(pullback_bear, {})[0].slug == "pullback_continuation_bearish"

    squeeze = build_candle_points(
        closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 116.2, 116.1, 116.15, 116.12, 116.18, 116.14, 116.16, 118.5],
        volumes=[1000.0] * 24 + [1700.0],
    )
    assert SqueezeBreakoutDetector().detect(squeeze, {})[0].slug == "squeeze_breakout"

    trend_pause = build_candle_points(
        closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 116.1, 116.0, 116.15, 116.05, 116.1, 116.12, 116.14, 116.16, 117.2, 118.0, 118.5],
        volumes=[1000.0] * 27 + [1600.0],
    )
    assert TrendPauseBreakoutDetector().detect(trend_pause, {})[0].slug == "trend_pause_breakout"

    handle_breakout = build_candle_points(
        closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 117.0, 118.0, 119.0, 120.0, 121.0, 122.0, 123.0, 124.0, 125.0, 126.0, 127.0, 128.0, 129.0, 130.0, 131.0, 132.0, 133.0, 134.0, 135.0, 134.5, 134.0, 133.8, 133.6, 133.5, 133.7, 133.9, 134.1, 134.3, 134.5, 134.7, 135.2, 136.5, 137.0],
        volumes=[1000.0] * 49 + [1500.0],
    )
    assert HandleBreakoutDetector().detect(handle_breakout, {})[0].slug == "handle_breakout"

    stair_step = build_candle_points(
        closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 113.0, 112.5, 113.5, 114.5, 115.5, 116.5, 115.2, 114.8, 115.8, 116.8, 117.8, 118.8, 119.0, 119.2, 120.5],
        volumes=[1000.0] * 29 + [1500.0],
    )
    assert StairStepContinuationDetector().detect(stair_step, {})[0].slug == "stair_step_continuation"
