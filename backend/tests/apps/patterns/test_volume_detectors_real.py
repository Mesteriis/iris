from dataclasses import replace

from iris.apps.patterns.domain.detectors.volume import (
    AccumulationDistributionDetector,
    ChurnBarDetector,
    ClimaxTurnDetector,
    EffortResultDivergenceDetector,
    RelativeVolumeBreakoutDetector,
    VolumeBreakoutConfirmationDetector,
    VolumeClimaxDetector,
    VolumeDivergenceDetector,
    VolumeDryUpDetector,
    VolumeFollowThroughDetector,
    VolumeSpikeDetector,
    VolumeTrendConfirmationDetector,
    build_volume_detectors,
)

from tests.factories.market_data import build_candle_points


def test_volume_detectors_short_inputs_return_empty() -> None:
    short = build_candle_points(closes=[100.0 + index for index in range(10)], volumes=[1000.0] * 10)
    for detector in build_volume_detectors():
        assert detector.detect(short, {}) == []


def test_volume_detectors_cover_real_breakout_and_flow_scenarios() -> None:
    spike = build_candle_points(closes=[100.0 + index * 0.8 for index in range(25)], volumes=[1000.0] * 24 + [2800.0])
    assert VolumeSpikeDetector().detect(spike, {})[0].slug == "volume_spike"

    climax = build_candle_points(closes=[100.0 + index * 1.2 for index in range(20)], volumes=[1000.0] * 19 + [4200.0])
    climax[-1] = replace(climax[-1], open=122.0, close=123.0, high=126.0, low=120.0, volume=4200.0)
    assert VolumeClimaxDetector().detect(climax, {})[0].slug == "volume_climax"

    divergence = build_candle_points(
        closes=[100.0 + index * 0.6 for index in range(30)] + [118.0, 119.0, 120.0, 121.0, 122.0, 123.0, 124.0, 125.0, 126.0, 127.0],
        volumes=[1000.0] * 20 + [2000.0] * 10 + [1200.0] * 10,
    )
    assert VolumeDivergenceDetector().detect(divergence, {})[0].slug == "volume_divergence"

    dry_up = build_candle_points(
        closes=[100.0 + 0.4 * index for index in range(15)] + [106.0, 106.1, 106.2, 106.15, 106.18, 106.2, 106.22, 106.24, 106.23, 106.3],
        volumes=[2000.0] * 24 + [700.0],
    )
    assert VolumeDryUpDetector().detect(dry_up, {})[0].slug == "volume_dry_up"

    breakout = build_candle_points(closes=[100.0 + 0.2 * index for index in range(24)] + [108.0], volumes=[1000.0] * 24 + [2500.0])
    assert VolumeBreakoutConfirmationDetector().detect(breakout, {})[0].slug == "volume_breakout_confirmation"
    assert RelativeVolumeBreakoutDetector().detect(build_candle_points(closes=[100.0 + 0.2 * index for index in range(19)] + [107.0], volumes=[1000.0] * 19 + [2600.0]), {})[0].slug == "relative_volume_breakout"

    accumulation = build_candle_points(
        closes=[100.0, 101.0, 100.5, 101.8, 101.2, 102.1, 101.9, 103.0, 102.5, 103.6, 103.1, 104.2, 103.8, 104.8, 104.4, 105.3, 104.9, 105.8, 105.5, 106.5],
        volumes=[1400.0, 1800.0, 1100.0, 1900.0, 1000.0, 2000.0, 1200.0, 2100.0, 1300.0, 2200.0, 1200.0, 2300.0, 1400.0, 2400.0, 1300.0, 2500.0, 1400.0, 2600.0, 1500.0, 2700.0],
    )
    assert AccumulationDistributionDetector("accumulation_volume", "bull").detect(accumulation, {})[0].slug == "accumulation_volume"

    distribution = build_candle_points(
        closes=[106.5, 105.8, 106.0, 105.1, 105.4, 104.5, 104.8, 103.9, 104.1, 103.2, 103.5, 102.6, 102.8, 101.9, 102.1, 101.2, 101.5, 100.6, 100.8, 99.8],
        volumes=[1400.0, 1800.0, 1100.0, 1900.0, 1000.0, 2000.0, 1200.0, 2100.0, 1300.0, 2200.0, 1200.0, 2300.0, 1400.0, 2400.0, 1300.0, 2500.0, 1400.0, 2600.0, 1500.0, 2700.0],
    )
    assert AccumulationDistributionDetector("distribution_volume", "bear").detect(distribution, {})[0].slug == "distribution_volume"

    churn = build_candle_points(closes=[100.0 + index for index in range(20)], volumes=[1000.0] * 19 + [3600.0])
    churn[-1] = replace(churn[-1], open=118.5, close=118.7, high=121.0, low=116.0, volume=3600.0)
    assert ChurnBarDetector().detect(churn, {})[0].slug == "churn_bar"

    effort_bull = build_candle_points(closes=[100.0 + index for index in range(18)], volumes=[1000.0] * 17 + [2600.0])
    effort_bull[-1] = replace(effort_bull[-1], open=116.0, close=119.0, high=119.8, low=115.5, volume=2600.0)
    assert EffortResultDivergenceDetector("effort_result_divergence_bullish", "bull").detect(effort_bull, {})[0].slug == "effort_result_divergence_bullish"

    effort_bear = build_candle_points(closes=[120.0 - index for index in range(18)], volumes=[1000.0] * 17 + [2600.0])
    effort_bear[-1] = replace(effort_bear[-1], open=104.0, close=101.0, high=104.4, low=100.3, volume=2600.0)
    assert EffortResultDivergenceDetector("effort_result_divergence_bearish", "bear").detect(effort_bear, {})[0].slug == "effort_result_divergence_bearish"

    follow_bull = build_candle_points(closes=[100.0 + 0.4 * index for index in range(12)], volumes=[1000.0] * 11 + [1800.0])
    follow_bull[-2] = replace(follow_bull[-2], open=103.5, close=105.0, high=105.2, low=103.0, volume=1000.0)
    follow_bull[-1] = replace(follow_bull[-1], open=105.1, close=106.0, high=106.2, low=104.8, volume=1800.0)
    assert VolumeFollowThroughDetector("volume_follow_through_bullish", "bull").detect(follow_bull, {})[0].slug == "volume_follow_through_bullish"

    follow_bear = build_candle_points(closes=[120.0 - 0.4 * index for index in range(12)], volumes=[1000.0] * 11 + [1800.0])
    follow_bear[-2] = replace(follow_bear[-2], open=116.5, close=115.0, high=116.8, low=114.9, volume=1000.0)
    follow_bear[-1] = replace(follow_bear[-1], open=114.8, close=114.0, high=115.0, low=113.8, volume=1800.0)
    assert VolumeFollowThroughDetector("volume_follow_through_bearish", "bear").detect(follow_bear, {})[0].slug == "volume_follow_through_bearish"

    buying_climax = build_candle_points(closes=[100.0 + index * 1.5 for index in range(16)], volumes=[1000.0] * 15 + [4000.0])
    buying_climax[-1] = replace(buying_climax[-1], open=123.0, close=121.0, high=124.0, low=120.0, volume=4000.0)
    assert ClimaxTurnDetector("buying_climax", "top").detect(buying_climax, {})[0].slug == "buying_climax"

    selling_climax = build_candle_points(closes=[140.0 - index * 1.5 for index in range(16)], volumes=[1000.0] * 15 + [4000.0])
    selling_climax[-1] = replace(selling_climax[-1], open=117.0, close=119.0, high=119.5, low=116.5, volume=4000.0)
    assert ClimaxTurnDetector("selling_climax", "bottom").detect(selling_climax, {})[0].slug == "selling_climax"

    trend_bull = build_candle_points(closes=[100.0 + index * 0.5 for index in range(25)], volumes=[1000.0] * 24 + [1500.0])
    assert VolumeTrendConfirmationDetector("volume_trend_confirmation_bullish", "bull").detect(trend_bull, {})[0].slug == "volume_trend_confirmation_bullish"

    trend_bear = build_candle_points(closes=[120.0 - index * 0.5 for index in range(25)], volumes=[1000.0] * 24 + [1500.0])
    assert VolumeTrendConfirmationDetector("volume_trend_confirmation_bearish", "bear").detect(trend_bear, {})[0].slug == "volume_trend_confirmation_bearish"


def test_volume_detectors_cover_negative_confirmation_paths() -> None:
    climax_fail = build_candle_points(closes=[100.0 + index * 1.2 for index in range(20)], volumes=[1000.0] * 19 + [4200.0])
    climax_fail[-1] = replace(climax_fail[-1], open=122.0, close=126.0, high=126.5, low=120.0, volume=4200.0)
    assert VolumeClimaxDetector().detect(climax_fail, {}) == []

    divergence_zero_previous = build_candle_points(
        closes=[100.0 + index * 0.6 for index in range(40)],
        volumes=[1000.0] * 20 + [0.0] * 10 + [1200.0] * 10,
    )
    assert VolumeDivergenceDetector().detect(divergence_zero_previous, {}) == []

    divergence_no_signal = build_candle_points(
        closes=[100.0 + index * 0.6 for index in range(40)],
        volumes=[1000.0] * 20 + [2000.0] * 10 + [1900.0] * 10,
    )
    assert VolumeDivergenceDetector().detect(divergence_no_signal, {}) == []

    dry_up_high_ratio = build_candle_points(
        closes=[100.0 + 0.4 * index for index in range(25)],
        volumes=[2000.0] * 24 + [1800.0],
    )
    assert VolumeDryUpDetector().detect(dry_up_high_ratio, {}) == []

    dry_up_lost_range = build_candle_points(
        closes=[100.0 + 0.4 * index for index in range(15)] + [106.0, 106.1, 106.2, 106.15, 106.18, 106.2, 106.22, 106.24, 106.23, 103.5],
        volumes=[2000.0] * 24 + [700.0],
    )
    assert VolumeDryUpDetector().detect(dry_up_lost_range, {}) == []

    breakout_fail = build_candle_points(closes=[100.0 + 0.2 * index for index in range(24)] + [104.5], volumes=[1000.0] * 24 + [2500.0])
    assert VolumeBreakoutConfirmationDetector().detect(breakout_fail, {}) == []

    accumulation_fail = build_candle_points(
        closes=[100.0, 101.0, 100.5, 101.8, 101.2, 102.1, 101.9, 103.0, 102.5, 103.6, 103.1, 104.2, 103.8, 104.8, 104.4, 105.3, 104.9, 105.8, 105.5, 99.0],
        volumes=[1400.0] * 20,
    )
    assert AccumulationDistributionDetector("accumulation_volume", "bull").detect(accumulation_fail, {}) == []

    distribution_fail = build_candle_points(
        closes=[106.5, 105.8, 106.0, 105.1, 105.4, 104.5, 104.8, 103.9, 104.1, 103.2, 103.5, 102.6, 102.8, 101.9, 102.1, 101.2, 101.5, 100.6, 100.8, 103.0],
        volumes=[1400.0] * 20,
    )
    assert AccumulationDistributionDetector("distribution_volume", "bear").detect(distribution_fail, {}) == []

    effort_bull_fail = build_candle_points(closes=[100.0 + index for index in range(18)], volumes=[1000.0] * 17 + [2600.0])
    effort_bull_fail[-1] = replace(effort_bull_fail[-1], open=116.0, close=119.0, high=123.0, low=115.5, volume=2600.0)
    assert EffortResultDivergenceDetector("effort_result_divergence_bullish", "bull").detect(effort_bull_fail, {}) == []

    effort_bear_fail = build_candle_points(closes=[120.0 - index for index in range(18)], volumes=[1000.0] * 17 + [2600.0])
    effort_bear_fail[-1] = replace(effort_bear_fail[-1], open=104.0, close=101.0, high=104.4, low=97.0, volume=2600.0)
    assert EffortResultDivergenceDetector("effort_result_divergence_bearish", "bear").detect(effort_bear_fail, {}) == []

    relative_breakout_fail = build_candle_points(closes=[100.0 + 0.2 * index for index in range(19)] + [103.5], volumes=[1000.0] * 19 + [2600.0])
    assert RelativeVolumeBreakoutDetector().detect(relative_breakout_fail, {}) == []

    follow_bull_fail = build_candle_points(closes=[100.0 + 0.4 * index for index in range(12)], volumes=[1000.0] * 11 + [1800.0])
    follow_bull_fail[-2] = replace(follow_bull_fail[-2], open=103.5, close=105.0, high=105.2, low=103.0, volume=1000.0)
    follow_bull_fail[-1] = replace(follow_bull_fail[-1], open=105.1, close=105.1, high=105.2, low=104.8, volume=1800.0)
    assert VolumeFollowThroughDetector("volume_follow_through_bullish", "bull").detect(follow_bull_fail, {}) == []

    follow_bear_fail = build_candle_points(closes=[120.0 - 0.4 * index for index in range(12)], volumes=[1000.0] * 11 + [1800.0])
    follow_bear_fail[-2] = replace(follow_bear_fail[-2], open=116.5, close=115.0, high=116.8, low=114.9, volume=1000.0)
    follow_bear_fail[-1] = replace(follow_bear_fail[-1], open=114.8, close=115.1, high=115.2, low=114.8, volume=1800.0)
    assert VolumeFollowThroughDetector("volume_follow_through_bearish", "bear").detect(follow_bear_fail, {}) == []

    buying_climax_fail = build_candle_points(closes=[100.0 + index * 1.5 for index in range(16)], volumes=[1000.0] * 15 + [4000.0])
    buying_climax_fail[-1] = replace(buying_climax_fail[-1], open=123.0, close=124.0, high=124.5, low=122.0, volume=4000.0)
    assert ClimaxTurnDetector("buying_climax", "top").detect(buying_climax_fail, {}) == []

    selling_climax_fail = build_candle_points(closes=[140.0 - index * 1.5 for index in range(16)], volumes=[1000.0] * 15 + [4000.0])
    selling_climax_fail[-1] = replace(selling_climax_fail[-1], open=117.0, close=116.0, high=117.5, low=115.5, volume=4000.0)
    assert ClimaxTurnDetector("selling_climax", "bottom").detect(selling_climax_fail, {}) == []

    trend_bull_fail = build_candle_points(closes=[100.0 + 0.05 * index for index in range(25)], volumes=[1000.0] * 24 + [1200.0])
    assert VolumeTrendConfirmationDetector("volume_trend_confirmation_bullish", "bull").detect(trend_bull_fail, {}) == []

    trend_bear_fail = build_candle_points(closes=[120.0 - 0.05 * index for index in range(25)], volumes=[1000.0] * 24 + [1200.0])
    assert VolumeTrendConfirmationDetector("volume_trend_confirmation_bearish", "bear").detect(trend_bear_fail, {}) == []
