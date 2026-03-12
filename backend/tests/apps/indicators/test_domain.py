from __future__ import annotations

import pytest

import app.apps.indicators.domain as indicator_domain
from app.apps.indicators.domain import adx_series, atr_series, bollinger_bands, ema_series, macd_series, rsi_series, sma_series


def test_indicator_math_moving_averages_and_macd() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]

    assert sma_series(values, 0) == [None] * 5
    assert sma_series(values, 3) == [None, None, 2.0, 3.0, 4.0]

    assert ema_series(values, 10) == [None] * 5
    assert ema_series(values, 3) == [None, None, 2.0, 3.0, 4.0]

    macd_line, signal_line, histogram = macd_series(values, fast_period=2, slow_period=3, signal_period=2)
    assert macd_line[:2] == [None, None]
    assert signal_line[:3] == [None, None, None]
    assert macd_line[-1] == pytest.approx(0.5)
    assert signal_line[-1] == pytest.approx(0.5)
    assert histogram[-1] == pytest.approx(0.0)


def test_indicator_math_rsi_handles_increasing_and_mixed_series() -> None:
    assert rsi_series([1.0, 2.0, 3.0], period=3) == [None, None, None]
    assert rsi_series([1.0, 2.0, 3.0, 4.0, 5.0], period=2) == [None, None, 100.0, 100.0, 100.0]

    mixed = rsi_series([1.0, 2.0, 1.0, 2.0, 1.0, 2.0], period=2)
    assert mixed[:2] == [None, None]
    assert mixed[2] == pytest.approx(50.0)
    assert 0.0 < mixed[-1] < 100.0


def test_indicator_math_atr_and_bollinger_cover_edge_cases() -> None:
    assert atr_series([2.0], [1.0], [1.5], period=2) == [None]

    atr = atr_series(
        highs=[10.0, 11.0, 12.0, 13.0],
        lows=[9.0, 10.0, 11.0, 12.0],
        closes=[9.5, 10.5, 11.5, 12.5],
        period=2,
    )
    assert atr == [None, pytest.approx(1.25), pytest.approx(1.375), pytest.approx(1.4375)]

    short_upper, short_middle, short_lower, short_width = bollinger_bands([1.0], period=2)
    assert short_upper == [None]
    assert short_middle == [None]
    assert short_lower == [None]
    assert short_width == [None]

    upper, middle, lower, width = bollinger_bands([1.0, 2.0, 3.0, 4.0], period=2)
    assert middle == [None, 1.5, 2.5, 3.5]
    assert upper[1] == pytest.approx(2.5)
    assert lower[1] == pytest.approx(0.5)
    assert width[1] == pytest.approx((2.5 - 0.5) / 1.5)

    _, zero_middle, _, zero_width = bollinger_bands([0.0, 0.0, 0.0], period=2)
    assert zero_middle == [None, 0.0, 0.0]
    assert zero_width == [None, None, None]


def test_indicator_math_adx_handles_flat_gap_and_trending_series() -> None:
    assert adx_series([2.0, 3.0, 4.0], [1.0, 2.0, 3.0], [1.5, 2.5, 3.5], period=2) == [None, None, None]

    flat = adx_series([1.0] * 6, [1.0] * 6, [1.0] * 6, period=3)
    assert flat == [None, None, None, None, None, None]

    gap_only = adx_series([2.0] * 5, [2.0] * 5, [2.0, 3.0, 2.0, 3.0, 2.0], period=2)
    assert gap_only[3] == pytest.approx(0.0)
    assert gap_only[4] == pytest.approx(0.0)

    trending = adx_series(
        highs=[10.0, 11.0, 12.5, 13.5, 15.0, 16.0, 17.0],
        lows=[9.0, 10.0, 11.0, 12.0, 13.5, 14.5, 15.5],
        closes=[9.5, 10.5, 12.0, 13.0, 14.5, 15.5, 16.5],
        period=2,
    )
    assert trending[3] is not None
    assert trending[-1] is not None
    assert trending[-1] > 0


def test_indicator_math_covers_remaining_guard_branches(monkeypatch) -> None:
    monkeypatch.setattr(indicator_domain, "sma_series", lambda values, period: [None] * len(values))
    upper, middle, lower, width = indicator_domain.bollinger_bands([1.0, 2.0, 3.0], period=2)
    assert upper == [None, None, None]
    assert middle == [None, None, None]
    assert lower == [None, None, None]
    assert width == [None, None, None]

    def fake_none_series(length: int) -> list[float | None]:
        if length == 5:
            return [None, None, 1.0, 1.0, None]
        return [None] * length

    monkeypatch.setattr(indicator_domain, "_none_series", fake_none_series)
    adx = indicator_domain.adx_series([1.0] * 5, [1.0] * 5, [1.0] * 5, period=2)
    assert adx[3] == pytest.approx(1.0)
    assert adx[4] is None
