import src.apps.patterns.domain.detectors.structural as structural_mod
from src.apps.patterns.domain.utils import Pivot
from tests.factories.market_data import build_candle_points


def _candles(*, length: int = 70, last: float = 100.0) -> list:
    closes = [100.0 + (index * 0.05) for index in range(length - 1)] + [last]
    return build_candle_points(closes=closes, volumes=[1000.0] * length)


def test_head_and_inverse_head_shoulders_guard_branches(monkeypatch) -> None:
    candles = _candles(last=95.0)

    def _set_find_pivots(highs: list[Pivot], lows: list[Pivot]) -> None:
        def _find(_values, *, kind: str, span: int = 2):
            del span
            return highs if kind == "high" else lows

        monkeypatch.setattr(structural_mod, "find_pivots", _find)

    head_shoulders = structural_mod.HeadShouldersDetector()
    _set_find_pivots([Pivot(10, 100.0), Pivot(20, 110.0)], [Pivot(15, 92.0)])
    assert head_shoulders.detect(candles, {}) == []

    _set_find_pivots(
        [Pivot(10, 100.0), Pivot(20, 101.0), Pivot(30, 100.5)],
        [Pivot(15, 92.0), Pivot(25, 91.5)],
    )
    assert head_shoulders.detect(candles, {}) == []

    _set_find_pivots(
        [Pivot(10, 100.0), Pivot(20, 110.0), Pivot(30, 94.0)],
        [Pivot(15, 92.0), Pivot(25, 91.5)],
    )
    assert head_shoulders.detect(candles, {}) == []

    monkeypatch.setattr(structural_mod, "within_tolerance", lambda left, right, tolerance: tolerance == 0.035)
    _set_find_pivots(
        [Pivot(10, 100.0), Pivot(20, 110.0), Pivot(30, 101.0)],
        [Pivot(9, 92.0), Pivot(31, 91.5)],
    )
    assert head_shoulders.detect(candles, {}) == []

    _set_find_pivots(
        [Pivot(10, 100.0), Pivot(20, 110.0), Pivot(30, 101.0)],
        [Pivot(15, 92.0), Pivot(25, 91.0)],
    )
    assert head_shoulders.detect(_candles(last=93.0), {}) == []

    inverse_head_shoulders = structural_mod.InverseHeadShouldersDetector()
    _set_find_pivots([Pivot(15, 110.0)], [Pivot(10, 100.0), Pivot(20, 90.0)])
    assert inverse_head_shoulders.detect(candles, {}) == []

    _set_find_pivots(
        [Pivot(15, 110.0), Pivot(25, 111.0)],
        [Pivot(10, 100.0), Pivot(20, 99.5), Pivot(30, 100.0)],
    )
    assert inverse_head_shoulders.detect(candles, {}) == []

    _set_find_pivots(
        [Pivot(15, 110.0), Pivot(25, 111.0)],
        [Pivot(10, 100.0), Pivot(20, 90.0), Pivot(30, 106.0)],
    )
    assert inverse_head_shoulders.detect(candles, {}) == []

    monkeypatch.setattr(structural_mod, "within_tolerance", lambda left, right, tolerance: False)
    _set_find_pivots(
        [Pivot(15, 110.0), Pivot(25, 111.0)],
        [Pivot(10, 100.0), Pivot(20, 90.0), Pivot(30, 99.0)],
    )
    assert inverse_head_shoulders.detect(candles, {}) == []

    monkeypatch.setattr(structural_mod, "within_tolerance", lambda left, right, tolerance: True)
    _set_find_pivots(
        [Pivot(9, 110.0), Pivot(31, 111.0)],
        [Pivot(10, 100.0), Pivot(20, 90.0), Pivot(30, 99.0)],
    )
    assert inverse_head_shoulders.detect(candles, {}) == []

    _set_find_pivots(
        [Pivot(9, 110.0), Pivot(31, 111.0)],
        [Pivot(10, 100.0), Pivot(20, 90.0), Pivot(30, 99.0)],
    )
    assert inverse_head_shoulders.detect(candles, {}) == []

    _set_find_pivots(
        [Pivot(15, 110.0), Pivot(25, 111.0)],
        [Pivot(10, 100.0), Pivot(20, 90.0), Pivot(30, 99.0)],
    )
    assert inverse_head_shoulders.detect(_candles(last=100.0), {}) == []


def test_multi_top_triangle_and_flat_base_guard_branches(monkeypatch) -> None:
    candles = _candles()

    double_top = structural_mod.MultiTopBottomDetector(slug="double_top", direction="top", touches=2)
    double_bottom = structural_mod.MultiTopBottomDetector(slug="double_bottom", direction="bottom", touches=2)

    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 39 + [95.0])
    monkeypatch.setattr(structural_mod, "find_pivots", lambda _values, *, kind, span=2: [Pivot(10, 110.0)] if kind == "high" else [Pivot(10, 90.0)])
    assert double_top.detect(candles, {}) == []

    monkeypatch.setattr(structural_mod, "find_pivots", lambda _values, *, kind, span=2: [Pivot(10, 110.0), Pivot(20, 103.0)] if kind == "high" else [Pivot(10, 90.0), Pivot(20, 91.0)])
    monkeypatch.setattr(structural_mod, "within_tolerance", lambda left, right, tolerance: tolerance == 0.035)
    assert double_top.detect(candles, {}) == []

    monkeypatch.setattr(structural_mod, "find_pivots", lambda _values, *, kind, span=2: [Pivot(10, 110.0), Pivot(20, 110.5)] if kind == "high" else [Pivot(10, 90.0), Pivot(20, 91.0)])
    monkeypatch.setattr(structural_mod, "within_tolerance", lambda left, right, tolerance: True)
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 39 + [101.0])
    assert double_top.detect(candles, {}) == []

    monkeypatch.setattr(structural_mod, "find_pivots", lambda _values, *, kind, span=2: [Pivot(10, 90.0), Pivot(20, 90.5)] if kind == "low" else [Pivot(10, 110.0), Pivot(20, 111.0)])
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 39 + [99.0])
    assert double_bottom.detect(candles, {}) == []

    ascending = structural_mod.TriangleDetector("ascending_triangle")
    descending = structural_mod.TriangleDetector("descending_triangle")
    symmetrical = structural_mod.TriangleDetector("symmetrical_triangle")

    monkeypatch.setattr(structural_mod, "highs", lambda _candles: [100.0] * 60)
    monkeypatch.setattr(structural_mod, "lows", lambda _candles: [95.0] * 60)
    monkeypatch.setattr(structural_mod, "find_pivots", lambda _values, *, kind, span=2: [Pivot(10, 100.0), Pivot(20, 101.0)] if kind == "high" else [Pivot(10, 95.0), Pivot(20, 94.5)])
    assert ascending.detect(candles, {}) == []

    def _triangle_pivots_compression(_values, *, kind: str, span: int = 2):
        del span
        if kind == "high":
            return [Pivot(10, 120.0), Pivot(20, 121.0), Pivot(30, 122.0)]
        return [Pivot(10, 100.0), Pivot(20, 99.0), Pivot(30, 98.0)]

    monkeypatch.setattr(structural_mod, "find_pivots", _triangle_pivots_compression)
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 59 + [100.0])
    assert ascending.detect(candles, {}) == []

    def _triangle_ascending_invalid(_values, *, kind: str, span: int = 2):
        del span
        if kind == "high":
            return [Pivot(10, 100.0), Pivot(20, 101.0), Pivot(30, 102.0)]
        return [Pivot(10, 98.0), Pivot(20, 99.0), Pivot(30, 100.0)]

    monkeypatch.setattr(structural_mod, "find_pivots", _triangle_ascending_invalid)
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 59 + [104.5])
    assert ascending.detect(_candles(last=104.5), {}) == []

    def _triangle_ascending_breakout(_values, *, kind: str, span: int = 2):
        del span
        if kind == "high":
            return [Pivot(10, 100.0), Pivot(20, 100.1), Pivot(30, 100.2)]
        return [Pivot(10, 96.0), Pivot(20, 97.0), Pivot(30, 98.0)]

    monkeypatch.setattr(structural_mod, "find_pivots", _triangle_ascending_breakout)
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 59 + [100.1])
    assert ascending.detect(candles, {}) == []

    def _triangle_desc_invalid(_values, *, kind: str, span: int = 2):
        del span
        if kind == "high":
            return [Pivot(10, 100.0), Pivot(20, 99.0), Pivot(30, 98.0)]
        return [Pivot(10, 95.0), Pivot(20, 94.0), Pivot(30, 93.0)]

    monkeypatch.setattr(structural_mod, "find_pivots", _triangle_desc_invalid)
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 59 + [94.5])
    assert descending.detect(candles, {}) == []

    def _triangle_desc_breakout(_values, *, kind: str, span: int = 2):
        del span
        if kind == "high":
            return [Pivot(10, 100.0), Pivot(20, 99.5), Pivot(30, 99.0)]
        return [Pivot(10, 95.0), Pivot(20, 95.02), Pivot(30, 95.01)]

    monkeypatch.setattr(structural_mod, "find_pivots", _triangle_desc_breakout)
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 59 + [95.5])
    assert descending.detect(candles, {}) == []

    def _triangle_sym_invalid(_values, *, kind: str, span: int = 2):
        del span
        if kind == "high":
            return [Pivot(10, 100.0), Pivot(20, 101.0), Pivot(30, 102.0)]
        return [Pivot(10, 95.0), Pivot(20, 96.0), Pivot(30, 97.0)]

    monkeypatch.setattr(structural_mod, "find_pivots", _triangle_sym_invalid)
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 59 + [98.0])
    assert symmetrical.detect(candles, {}) == []

    def _triangle_sym_no_breakout(_values, *, kind: str, span: int = 2):
        del span
        if kind == "high":
            return [Pivot(10, 100.0), Pivot(20, 99.5), Pivot(30, 99.0)]
        return [Pivot(10, 95.0), Pivot(20, 95.5), Pivot(30, 96.0)]

    monkeypatch.setattr(structural_mod, "find_pivots", _triangle_sym_no_breakout)
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 59 + [97.0])
    assert symmetrical.detect(candles, {}) == []

    flat_base = structural_mod.FlatBaseDetector()
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0 + (index * 0.05) for index in range(35)])
    assert flat_base.detect(_candles(length=35, last=101.7), {}) == []

    monkeypatch.setattr(
        structural_mod,
        "closes",
        lambda _candles: [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 114.0, 110.0, 115.0, 109.0, 116.0, 108.0, 116.5, 108.5, 116.0, 109.0, 115.5, 109.5, 115.0, 110.0, 114.5, 110.5, 114.0, 111.0, 114.0, 115.0],
    )
    assert flat_base.detect(_candles(length=35, last=115.0), {}) == []

    monkeypatch.setattr(
        structural_mod,
        "closes",
        lambda _candles: [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 114.2, 114.4, 114.6, 114.7, 114.8, 114.9, 115.0, 115.1, 115.2, 115.1, 115.0, 114.95, 114.98, 115.05, 115.1, 115.15, 115.2, 115.25, 115.2, 115.2],
    )
    assert flat_base.detect(_candles(length=35, last=115.2), {}) == []


def test_wedge_rectangle_broadening_and_expanding_triangle_guard_branches(monkeypatch) -> None:
    candles = _candles()

    monkeypatch.setattr(structural_mod, "highs", lambda _candles: [110.0] * 45)
    monkeypatch.setattr(structural_mod, "lows", lambda _candles: [100.0] * 45)
    rising_wedge = structural_mod.WedgeDetector("rising_wedge")
    falling_wedge = structural_mod.WedgeDetector("falling_wedge")
    assert rising_wedge.detect(candles, {}) == []

    monkeypatch.setattr(structural_mod, "highs", lambda _candles: [120.0] * 15 + [111.0] * 15)
    monkeypatch.setattr(structural_mod, "lows", lambda _candles: [100.0] * 15 + [108.0] * 15)
    slope_values = iter([1.0, 0.5])
    monkeypatch.setattr(structural_mod, "linear_slope", lambda _values: next(slope_values))
    assert rising_wedge.detect(_candles(last=107.0), {}) == []

    slope_values = iter([1.0, 2.0])
    monkeypatch.setattr(structural_mod, "linear_slope", lambda _values: next(slope_values))
    assert rising_wedge.detect(_candles(last=109.0), {}) == []

    slope_values = iter([-0.5, -1.0])
    monkeypatch.setattr(structural_mod, "linear_slope", lambda _values: next(slope_values))
    assert falling_wedge.detect(_candles(last=111.5), {}) == []

    slope_values = iter([-2.0, -1.0])
    monkeypatch.setattr(structural_mod, "linear_slope", lambda _values: next(slope_values))
    assert falling_wedge.detect(_candles(last=110.5), {}) == []

    rectangle_top = structural_mod.RectangleDetector("rectangle_top", "top")
    rectangle_bottom = structural_mod.RectangleDetector("rectangle_bottom", "bottom")
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0 + index for index in range(45)])
    assert rectangle_top.detect(_candles(length=45, last=144.0), {}) == []

    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0, 101.0, 102.0, 103.0] * 11 + [102.0])
    monkeypatch.setattr(structural_mod, "find_pivots", lambda _values, *, kind, span=2: [Pivot(10, 103.0)] if kind == "high" else [Pivot(10, 100.0)])
    assert rectangle_top.detect(_candles(length=45, last=99.0), {}) == []

    monkeypatch.setattr(structural_mod, "find_pivots", lambda _values, *, kind, span=2: [Pivot(10, 103.0), Pivot(20, 103.0)] if kind == "high" else [Pivot(10, 100.0), Pivot(20, 100.0)])
    assert rectangle_top.detect(_candles(length=45, last=100.0), {}) == []
    assert rectangle_bottom.detect(_candles(length=45, last=103.0), {}) == []

    broadening_top = structural_mod.BroadeningDetector("broadening_top", "top")
    broadening_bottom = structural_mod.BroadeningDetector("broadening_bottom", "bottom")
    monkeypatch.setattr(structural_mod, "highs", lambda _candles: [105.0] * 50)
    monkeypatch.setattr(structural_mod, "lows", lambda _candles: [95.0] * 50)
    assert broadening_top.detect(_candles(length=50, last=94.0), {}) == []

    monkeypatch.setattr(structural_mod, "highs", lambda _candles: [105.0] * 20 + [110.0] * 20 + [112.0] * 10)
    monkeypatch.setattr(structural_mod, "lows", lambda _candles: [95.0] * 20 + [90.0] * 20 + [92.0] * 10)
    assert broadening_top.detect(_candles(length=50, last=93.0), {}) == []
    assert broadening_bottom.detect(_candles(length=50, last=111.0), {}) == []

    expanding = structural_mod.ExpandingTriangleDetector()
    monkeypatch.setattr(structural_mod, "find_pivots", lambda _values, *, kind, span=2: [Pivot(10, 100.0), Pivot(20, 101.0)] if kind == "high" else [Pivot(10, 95.0), Pivot(20, 94.0)])
    monkeypatch.setattr(structural_mod, "highs", lambda _candles: [100.0] * 55)
    monkeypatch.setattr(structural_mod, "lows", lambda _candles: [95.0] * 55)
    assert expanding.detect(_candles(length=55, last=101.0), {}) == []

    def _expanding_not_widening(_values, *, kind: str, span: int = 2):
        del span
        if kind == "high":
            return [Pivot(10, 105.0), Pivot(20, 106.0), Pivot(30, 104.0)]
        return [Pivot(10, 95.0), Pivot(20, 94.0), Pivot(30, 96.0)]

    monkeypatch.setattr(structural_mod, "find_pivots", _expanding_not_widening)
    assert expanding.detect(_candles(length=55, last=103.0), {}) == []

    def _expanding_small_range(_values, *, kind: str, span: int = 2):
        del span
        if kind == "high":
            return [Pivot(10, 100.0), Pivot(20, 100.2), Pivot(30, 100.4)]
        return [Pivot(10, 95.0), Pivot(20, 94.9), Pivot(30, 94.8)]

    monkeypatch.setattr(structural_mod, "find_pivots", _expanding_small_range)
    assert expanding.detect(_candles(length=55, last=103.0), {}) == []

    def _expanding_no_breakout(_values, *, kind: str, span: int = 2):
        del span
        if kind == "high":
            return [Pivot(10, 100.0), Pivot(20, 102.0), Pivot(30, 110.0)]
        return [Pivot(10, 95.0), Pivot(20, 93.0), Pivot(30, 90.0)]

    monkeypatch.setattr(structural_mod, "find_pivots", _expanding_no_breakout)
    assert expanding.detect(_candles(length=55, last=100.0), {}) == []


def test_channel_rounded_and_diamond_guard_branches(monkeypatch) -> None:
    candles = _candles()

    bull_channel = structural_mod.ChannelBreakDetector("descending_channel_breakout", "bull")
    bear_channel = structural_mod.ChannelBreakDetector("ascending_channel_breakdown", "bear")
    monkeypatch.setattr(structural_mod, "highs", lambda _candles: [110.0] * 45)
    monkeypatch.setattr(structural_mod, "lows", lambda _candles: [100.0] * 45)
    monkeypatch.setattr(structural_mod, "within_tolerance", lambda left, right, tolerance: False)
    assert bull_channel.detect(candles, {}) == []

    monkeypatch.setattr(structural_mod, "within_tolerance", lambda left, right, tolerance: True)
    slope_values = iter([-1.0, -1.0])
    monkeypatch.setattr(structural_mod, "linear_slope", lambda _values: next(slope_values))
    assert bull_channel.detect(_candles(last=109.0), {}) == []

    slope_values = iter([1.0, 1.0])
    monkeypatch.setattr(structural_mod, "linear_slope", lambda _values: next(slope_values))
    assert bear_channel.detect(_candles(last=101.0), {}) == []

    rounded_bottom = structural_mod.RoundedTurnDetector("rounded_bottom", "bottom")
    rounded_top = structural_mod.RoundedTurnDetector("rounded_top", "top")
    monkeypatch.setattr(structural_mod, "within_tolerance", lambda left, right, tolerance: False)
    assert rounded_bottom.detect(_candles(length=70, last=101.0), {}) == []

    monkeypatch.setattr(structural_mod, "within_tolerance", lambda left, right, tolerance: True)
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 20 + [95.0] * 30 + [100.0] * 20)
    assert rounded_bottom.detect(_candles(length=70, last=99.0), {}) == []

    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 20 + [109.0] * 30 + [100.0] * 20)
    assert rounded_top.detect(_candles(length=70, last=101.0), {}) == []

    diamond_bottom = structural_mod.DiamondDetector("diamond_bottom", "bottom")
    diamond_top = structural_mod.DiamondDetector("diamond_top", "top")
    monkeypatch.setattr(structural_mod, "closes", lambda _candles: [100.0] * 60)
    assert diamond_bottom.detect(_candles(length=60, last=100.0), {}) == []

    range_values = iter([10.0, 20.0, 5.0])
    monkeypatch.setattr(structural_mod, "window_range", lambda _values: next(range_values))
    monkeypatch.setattr(
        structural_mod,
        "closes",
        lambda _candles: [100.0] * 18 + [95.0, 94.0, 93.0, 92.0, 91.0, 90.0, 89.0, 90.0, 91.0, 92.0, 93.0, 94.0, 95.0, 96.0, 97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0] + [101.0, 100.5, 100.0, 99.5, 99.0, 98.5, 98.0, 97.5, 97.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0],
    )
    assert diamond_bottom.detect(_candles(length=60, last=99.0), {}) == []

    monkeypatch.setattr(structural_mod, "window_range", lambda values: max(values) - min(values) if values else 0.0)
    monkeypatch.setattr(
        structural_mod,
        "closes",
        lambda _candles: [100.0] * 18 + [95.0, 94.0, 93.0, 92.0, 91.0, 90.0, 89.0, 90.0, 91.0, 92.0, 93.0, 94.0, 95.0, 96.0, 97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0] + [101.0] * 18,
    )
    assert diamond_bottom.detect(_candles(length=60, last=100.0), {}) == []

    range_values = iter([10.0, 20.0, 5.0])
    monkeypatch.setattr(structural_mod, "window_range", lambda _values: next(range_values))
    monkeypatch.setattr(
        structural_mod,
        "closes",
        lambda _candles: [100.0] * 18 + [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 106.0, 105.0, 104.0, 103.0, 102.0, 101.0, 100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0, 91.0, 90.0] + [95.0, 94.5, 94.0, 93.5, 93.0, 92.5, 92.0, 91.5, 91.0, 95.0, 95.0, 95.0, 95.0, 95.0, 95.0, 95.0, 95.0, 95.0],
    )
    assert diamond_top.detect(_candles(length=60, last=95.0), {}) == []

    monkeypatch.setattr(structural_mod, "window_range", lambda values: max(values) - min(values) if values else 0.0)
    monkeypatch.setattr(
        structural_mod,
        "closes",
        lambda _candles: [100.0] * 18 + [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 106.0, 105.0, 104.0, 103.0, 102.0, 101.0, 100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0, 91.0, 90.0] + [99.0] * 18,
    )
    assert diamond_top.detect(_candles(length=60, last=100.0), {}) == []
