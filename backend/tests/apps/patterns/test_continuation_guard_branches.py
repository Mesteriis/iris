import src.apps.patterns.domain.detectors.continuation as continuation_mod

from tests.factories.market_data import build_candle_points


def _candles(*, closes: list[float]) -> list:
    return build_candle_points(closes=closes, volumes=[1000.0] * (len(closes) - 1) + [1500.0])


def test_flag_pennant_and_cup_handle_guard_branches() -> None:
    bull_flag = continuation_mod.FlagDetector("bull_flag", "bull")
    bear_flag = continuation_mod.FlagDetector("bear_flag", "bear")
    invalid_bull = _candles(closes=[100.0 + (index * 0.4) for index in range(35)])
    assert bull_flag.detect(invalid_bull, {}) == []

    bull_no_break = _candles(
        closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 112.0, 114.0, 116.0, 118.0, 120.0, 122.0, 124.0, 126.0, 127.0, 128.0, 127.0, 126.0, 125.0, 124.0, 123.0, 122.0, 121.5, 121.0, 120.5, 120.0, 119.5, 119.0, 118.5, 118.0]
    )
    assert bull_flag.detect(bull_no_break, {}) == []

    invalid_bear = _candles(closes=[140.0 - (index * 0.4) for index in range(35)])
    assert bear_flag.detect(invalid_bear, {}) == []

    bear_no_break = _candles(
        closes=[130.0, 129.0, 128.0, 127.0, 126.0, 125.0, 124.0, 123.0, 122.0, 121.0, 120.0, 118.0, 116.0, 114.0, 112.0, 110.0, 108.0, 106.0, 104.0, 103.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 108.5, 109.0, 109.5, 110.0, 110.5, 111.0, 111.5, 112.0]
    )
    assert bear_flag.detect(bear_no_break, {}) == []

    pennant_no_breakout = _candles(closes=[100.0 + index * 1.8 for index in range(20)] + [136.0, 136.2, 136.4, 136.1, 136.0, 135.9, 136.0, 136.1, 136.2, 136.3])
    assert continuation_mod.PennantDetector().detect(pennant_no_breakout, {}) == []

    cup_handle = continuation_mod.CupAndHandleDetector()
    shallow_cup = _candles(closes=[120.0] * 20 + [118.0] * 40 + [120.0] * 20)
    assert cup_handle.detect(shallow_cup, {}) == []

    asymmetric_cup = _candles(closes=[130.0] * 20 + [100.0] * 40 + [120.0] * 20)
    assert cup_handle.detect(asymmetric_cup, {}) == []

    deep_handle = _candles(
        closes=[126.0] * 20 + [110.0, 108.0, 106.0, 104.0, 102.0, 100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 114.0, 116.0, 118.0, 120.0, 122.0, 124.0, 126.0, 126.0, 125.5, 124.0, 122.0, 120.0, 118.0, 116.0, 114.0, 112.0, 111.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 118.0, 120.0, 123.0, 126.0]
    )
    assert cup_handle.detect(deep_handle, {}) == []

    no_breakout_cup = _candles(
        closes=[126.0] * 20 + [121.0, 119.0, 117.0, 115.0, 113.0, 111.0, 109.0, 107.0, 105.0, 103.0, 101.0, 100.0, 101.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 114.0, 116.0, 118.0, 120.0, 122.0, 123.0, 124.0, 125.0, 126.0, 125.8, 125.6, 125.4, 125.2, 125.0, 124.8, 124.6, 124.8, 125.0, 125.2, 125.5, 125.8]
    )
    assert cup_handle.detect(no_breakout_cup, {}) == []


def test_bear_flag_reaches_no_break_branch(monkeypatch) -> None:
    detector = continuation_mod.FlagDetector("bear_flag", "bear")
    candles = _candles(closes=[120.0] * 35)
    monkeypatch.setattr(
        continuation_mod,
        "closes",
        lambda _candles: [130.0, 129.0, 128.0, 127.0, 126.0, 125.0, 124.0, 123.0, 122.0, 121.0, 120.0, 118.0, 116.0, 114.0, 112.0, 110.0, 108.0, 106.0, 104.0, 103.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 108.5, 109.0, 109.5, 110.0, 110.5, 111.0, 111.5, 111.0],
    )
    assert detector.detect(candles, {}) == []


def test_breakout_consolidation_high_tight_and_channel_guard_branches() -> None:
    breakout = continuation_mod.BreakoutRetestDetector()
    assert breakout.detect(_candles(closes=[100.0, 100.4, 100.8, 101.2, 101.6, 102.0, 102.4, 102.8, 103.2, 103.6, 104.0, 104.4, 104.8, 105.2, 105.6, 106.0, 106.4, 106.8, 107.2, 107.6, 108.0, 108.4, 108.8, 109.2, 109.6, 110.5, 111.0, 111.5, 108.0, 107.0, 106.0, 106.5, 107.0, 107.5, 108.0, 108.5, 109.0, 109.5, 110.0, 110.5]), {}) == []

    consolidation = continuation_mod.ConsolidationBreakoutDetector()
    assert consolidation.detect(_candles(closes=[100.0 + index for index in range(24)]), {}) == []
    assert consolidation.detect(_candles(closes=[100.0 + (0.1 * index) for index in range(23)] + [102.2]), {}) == []

    high_tight = continuation_mod.HighTightFlagDetector()
    assert high_tight.detect(_candles(closes=[100.0 + (index * 0.5) for index in range(32)]), {}) == []

    bull_channel = continuation_mod.ChannelContinuationDetector("falling_channel_breakout", "bull")
    bear_channel = continuation_mod.ChannelContinuationDetector("rising_channel_breakdown", "bear")
    assert bull_channel.detect(_candles(closes=[100.0 + (index * 0.2) for index in range(45)]), {}) == []
    assert bear_channel.detect(_candles(closes=[130.0 - (index * 0.2) for index in range(45)]), {}) == []


def test_measured_base_and_volatility_contraction_guard_branches() -> None:
    bull_measured = continuation_mod.MeasuredMoveDetector("measured_move_bullish", "bull")
    bear_measured = continuation_mod.MeasuredMoveDetector("measured_move_bearish", "bear")
    assert bull_measured.detect(_candles(closes=[100.0 + (index * 0.4) for index in range(40)]), {}) == []
    assert bear_measured.detect(_candles(closes=[130.0 - (index * 0.4) for index in range(40)]), {}) == []

    base_breakout = continuation_mod.BaseBreakoutDetector()
    assert base_breakout.detect(_candles(closes=[100.0 + (index * 0.1) for index in range(34)]), {}) == []
    assert base_breakout.detect(_candles(closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 114.2, 114.4, 114.6, 114.7, 114.8, 114.9, 115.0, 115.1, 115.2, 115.1, 115.0, 114.95, 114.98, 115.05, 115.1, 115.15, 115.2, 115.25, 115.2]), {}) == []

    vcb_bull = continuation_mod.VolatilityContractionBreakDetector("volatility_contraction_breakout", "bull")
    vcb_bear = continuation_mod.VolatilityContractionBreakDetector("volatility_contraction_breakdown", "bear")
    assert vcb_bull.detect(_candles(closes=[100.0, 101.0, 99.0, 102.0, 98.0, 103.0, 97.0, 104.0, 96.0, 105.0, 95.0, 106.0] * 3), {}) == []
    assert vcb_bull.detect(_candles(closes=[100.0, 102.0, 98.0, 103.0, 97.0, 104.0, 96.0, 105.0, 95.0, 106.0, 94.0, 107.0, 100.0, 101.0, 99.5, 100.5, 100.2, 99.8, 100.3, 100.0, 99.9, 100.1, 100.05, 100.0, 100.1, 100.2, 100.0, 100.1, 100.15, 100.1, 100.12, 100.14, 100.16, 100.18, 100.2, 100.19]), {}) == []
    assert vcb_bear.detect(_candles(closes=[120.0, 118.0, 122.0, 117.0, 123.0, 116.0, 124.0, 115.0, 125.0, 114.0, 126.0, 113.0, 120.0, 119.0, 120.5, 119.5, 120.2, 119.8, 120.1, 120.0, 120.05, 119.95, 120.0, 119.98, 120.02, 120.0, 119.99, 120.01, 120.0, 119.98, 119.96, 119.94, 119.92, 119.9, 119.88, 119.89]), {}) == []


def test_pullback_squeeze_trend_pause_handle_and_stair_step_guard_branches() -> None:
    pullback_bull = continuation_mod.PullbackContinuationDetector("pullback_continuation_bullish", "bull")
    pullback_bear = continuation_mod.PullbackContinuationDetector("pullback_continuation_bearish", "bear")
    assert pullback_bull.detect(_candles(closes=[100.0 + (index * 0.4) for index in range(30)]), {}) == []
    assert pullback_bear.detect(_candles(closes=[130.0 - (index * 0.4) for index in range(30)]), {}) == []

    squeeze = continuation_mod.SqueezeBreakoutDetector()
    assert squeeze.detect(_candles(closes=[100.0 + (index * 0.6) for index in range(25)]), {}) == []
    assert squeeze.detect(_candles(closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 116.2, 116.1, 116.15, 116.12, 116.18, 116.14, 116.16, 116.15]), {}) == []

    trend_pause = continuation_mod.TrendPauseBreakoutDetector()
    assert trend_pause.detect(_candles(closes=[100.0 + (index * 0.2) for index in range(28)]), {}) == []

    handle_breakout = continuation_mod.HandleBreakoutDetector()
    deep_handle = _candles(closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 117.0, 118.0, 119.0, 120.0, 121.0, 122.0, 123.0, 124.0, 125.0, 126.0, 127.0, 128.0, 129.0, 130.0, 131.0, 132.0, 133.0, 134.0, 135.0, 125.0, 124.0, 123.5, 123.0, 122.5, 122.0, 121.5, 121.0, 120.5, 120.0, 119.5, 119.0, 118.5, 118.0])
    assert handle_breakout.detect(deep_handle, {}) == []
    no_breakout_handle = _candles(closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 117.0, 118.0, 119.0, 120.0, 121.0, 122.0, 123.0, 124.0, 125.0, 126.0, 127.0, 128.0, 129.0, 130.0, 131.0, 132.0, 133.0, 134.0, 135.0, 134.5, 134.0, 133.8, 133.6, 133.5, 133.7, 133.9, 134.1, 134.3, 134.5, 134.7, 134.8, 134.9, 135.0])
    assert handle_breakout.detect(no_breakout_handle, {}) == []

    stair_step = continuation_mod.StairStepContinuationDetector()
    assert stair_step.detect(_candles(closes=[100.0] * 30), {}) == []
