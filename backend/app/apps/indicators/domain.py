from __future__ import annotations

from collections.abc import Sequence
from math import fabs
from statistics import pstdev


def _none_series(length: int) -> list[float | None]:
    return [None] * length


def sma_series(values: Sequence[float], period: int) -> list[float | None]:
    result = _none_series(len(values))
    if period <= 0 or len(values) < period:
        return result
    rolling_sum = sum(values[:period])
    result[period - 1] = rolling_sum / period
    for index in range(period, len(values)):
        rolling_sum += values[index] - values[index - period]
        result[index] = rolling_sum / period
    return result


def ema_series(values: Sequence[float], period: int) -> list[float | None]:
    result = _none_series(len(values))
    if period <= 0 or len(values) < period:
        return result
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    multiplier = 2 / (period + 1)
    ema_value = seed
    for index in range(period, len(values)):
        ema_value = (values[index] - ema_value) * multiplier + ema_value
        result[index] = ema_value
    return result


def rsi_series(values: Sequence[float], period: int = 14) -> list[float | None]:
    result = _none_series(len(values))
    if len(values) <= period:
        return result

    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, len(values)):
        delta = values[index] - values[index - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))

    for index in range(period + 1, len(values)):
        gain = gains[index - 1]
        loss = losses[index - 1]
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        if avg_loss == 0:
            result[index] = 100.0
            continue
        rs = avg_gain / avg_loss
        result[index] = 100 - (100 / (1 + rs))
    return result


def macd_series(
    values: Sequence[float],
    *,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    fast = ema_series(values, fast_period)
    slow = ema_series(values, slow_period)
    macd_line = _none_series(len(values))
    macd_compact: list[float] = []
    macd_indices: list[int] = []
    for index, (fast_value, slow_value) in enumerate(zip(fast, slow, strict=False)):
        if fast_value is None or slow_value is None:
            continue
        value = fast_value - slow_value
        macd_line[index] = value
        macd_compact.append(value)
        macd_indices.append(index)

    signal_compact = ema_series(macd_compact, signal_period)
    signal_line = _none_series(len(values))
    histogram = _none_series(len(values))
    for compact_index, series_index in enumerate(macd_indices):
        signal_value = signal_compact[compact_index]
        if signal_value is None:
            continue
        signal_line[series_index] = signal_value
        histogram[series_index] = macd_line[series_index] - signal_value if macd_line[series_index] is not None else None
    return macd_line, signal_line, histogram


def atr_series(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> list[float | None]:
    result = _none_series(len(closes))
    if len(closes) < period + 1:
        return result

    true_ranges: list[float] = [highs[0] - lows[0]]
    for index in range(1, len(closes)):
        true_ranges.append(
            max(
                highs[index] - lows[index],
                fabs(highs[index] - closes[index - 1]),
                fabs(lows[index] - closes[index - 1]),
            )
        )

    atr_value = sum(true_ranges[:period]) / period
    result[period - 1] = atr_value
    for index in range(period, len(true_ranges)):
        atr_value = ((atr_value * (period - 1)) + true_ranges[index]) / period
        result[index] = atr_value
    return result


def bollinger_bands(
    values: Sequence[float],
    *,
    period: int = 20,
    stddev_multiplier: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None], list[float | None]]:
    upper = _none_series(len(values))
    middle = sma_series(values, period)
    lower = _none_series(len(values))
    width = _none_series(len(values))
    if len(values) < period:
        return upper, middle, lower, width

    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        mean = middle[index]
        if mean is None:
            continue
        deviation = pstdev(window)
        upper[index] = mean + stddev_multiplier * deviation
        lower[index] = mean - stddev_multiplier * deviation
        width[index] = ((upper[index] - lower[index]) / mean) if mean != 0 else None
    return upper, middle, lower, width


def adx_series(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> list[float | None]:
    result = _none_series(len(closes))
    if len(closes) < (period * 2):
        return result

    tr: list[float] = [0.0]
    plus_dm: list[float] = [0.0]
    minus_dm: list[float] = [0.0]
    for index in range(1, len(closes)):
        up_move = highs[index] - highs[index - 1]
        down_move = lows[index - 1] - lows[index]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        tr.append(
            max(
                highs[index] - lows[index],
                fabs(highs[index] - closes[index - 1]),
                fabs(lows[index] - closes[index - 1]),
            )
        )

    tr_smooth = sum(tr[1 : period + 1])
    plus_smooth = sum(plus_dm[1 : period + 1])
    minus_smooth = sum(minus_dm[1 : period + 1])
    dx_values: list[float | None] = _none_series(len(closes))

    for index in range(period, len(closes)):
        if index > period:
            tr_smooth = tr_smooth - (tr_smooth / period) + tr[index]
            plus_smooth = plus_smooth - (plus_smooth / period) + plus_dm[index]
            minus_smooth = minus_smooth - (minus_smooth / period) + minus_dm[index]

        if tr_smooth == 0:
            continue
        plus_di = 100 * (plus_smooth / tr_smooth)
        minus_di = 100 * (minus_smooth / tr_smooth)
        di_sum = plus_di + minus_di
        if di_sum == 0:
            dx_values[index] = 0.0
            continue
        dx_values[index] = 100 * fabs(plus_di - minus_di) / di_sum

    seed_window = [value for value in dx_values[period : period * 2] if value is not None]
    if len(seed_window) < period:
        return result
    adx_value = sum(seed_window) / period
    result[(period * 2) - 1] = adx_value
    for index in range(period * 2, len(closes)):
        value = dx_values[index]
        if value is None:
            continue
        adx_value = ((adx_value * (period - 1)) + value) / period
        result[index] = adx_value
    return result
