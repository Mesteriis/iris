from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from statistics import mean
from typing import Sequence

from app.apps.market_data.repos import CandlePoint, candle_close_timestamp
from app.apps.indicators.domain import adx_series, atr_series, bollinger_bands, ema_series, macd_series, rsi_series, sma_series


@dataclass(slots=True, frozen=True)
class Pivot:
    index: int
    price: float


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous


def average(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(mean(values))


def closes(candles: Sequence[CandlePoint]) -> list[float]:
    return [float(item.close) for item in candles]


def highs(candles: Sequence[CandlePoint]) -> list[float]:
    return [float(item.high) for item in candles]


def lows(candles: Sequence[CandlePoint]) -> list[float]:
    return [float(item.low) for item in candles]


def volumes(candles: Sequence[CandlePoint]) -> list[float]:
    return [float(item.volume or 0.0) for item in candles]


def infer_timeframe(candles: Sequence[CandlePoint]) -> int:
    if len(candles) < 2:
        return 15
    delta = candles[-1].timestamp - candles[-2].timestamp
    minutes = int(delta / timedelta(minutes=1))
    return minutes if minutes > 0 else 15


def signal_timestamp(candles: Sequence[CandlePoint]) -> object:
    return candle_close_timestamp(candles[-1].timestamp, infer_timeframe(candles))


def linear_slope(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    count = len(values)
    mean_x = (count - 1) / 2
    mean_y = average(values)
    numerator = sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values))
    denominator = sum((index - mean_x) ** 2 for index in range(count))
    return numerator / denominator


def find_pivots(
    values: Sequence[float],
    *,
    kind: str,
    span: int = 2,
) -> list[Pivot]:
    pivots: list[Pivot] = []
    if len(values) < (span * 2) + 1:
        return pivots
    for index in range(span, len(values) - span):
        center = values[index]
        left = values[index - span : index]
        right = values[index + 1 : index + span + 1]
        if kind == "high" and center >= max(left) and center >= max(right):
            pivots.append(Pivot(index=index, price=center))
        if kind == "low" and center <= min(left) and center <= min(right):
            pivots.append(Pivot(index=index, price=center))
    return pivots


def within_tolerance(left: float, right: float, tolerance: float) -> bool:
    if left == right:
        return True
    baseline = max(abs(left), abs(right), 1e-9)
    return abs(left - right) / baseline <= tolerance


def window_range(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return max(values) - min(values)


def volume_ratio(candles: Sequence[CandlePoint], lookback: int = 20) -> float:
    if not candles:
        return 0.0
    current = float(candles[-1].volume or 0.0)
    baseline_window = [float(item.volume or 0.0) for item in candles[-(lookback + 1) : -1]]
    baseline = average(baseline_window)
    if baseline <= 0:
        return 0.0
    return current / baseline


def current_indicator_map(candles: Sequence[CandlePoint]) -> dict[str, float | None]:
    close_values = closes(candles)
    high_values = highs(candles)
    low_values = lows(candles)
    volume_values = volumes(candles)

    ema_20 = ema_series(close_values, 20)
    ema_50 = ema_series(close_values, 50)
    ema_200 = ema_series(close_values, 200)
    sma_50 = sma_series(close_values, 50)
    sma_200 = sma_series(close_values, 200)
    rsi_14 = rsi_series(close_values, 14)
    macd, macd_signal, macd_histogram = macd_series(close_values)
    atr_14 = atr_series(high_values, low_values, close_values, 14)
    bb_upper, bb_middle, bb_lower, bb_width = bollinger_bands(close_values, period=20)
    adx_14 = adx_series(high_values, low_values, close_values, 14)

    return {
        "price_current": close_values[-1] if close_values else None,
        "ema_20": ema_20[-1] if ema_20 else None,
        "ema_50": ema_50[-1] if ema_50 else None,
        "ema_200": ema_200[-1] if ema_200 else None,
        "sma_50": sma_50[-1] if sma_50 else None,
        "sma_200": sma_200[-1] if sma_200 else None,
        "rsi_14": rsi_14[-1] if rsi_14 else None,
        "macd": macd[-1] if macd else None,
        "macd_signal": macd_signal[-1] if macd_signal else None,
        "macd_histogram": macd_histogram[-1] if macd_histogram else None,
        "prev_atr_14": atr_14[-2] if len(atr_14) > 1 else None,
        "atr_14": atr_14[-1] if atr_14 else None,
        "bb_upper": bb_upper[-1] if bb_upper else None,
        "bb_middle": bb_middle[-1] if bb_middle else None,
        "bb_lower": bb_lower[-1] if bb_lower else None,
        "prev_bb_width": bb_width[-2] if len(bb_width) > 1 else None,
        "bb_width": bb_width[-1] if bb_width else None,
        "adx_14": adx_14[-1] if adx_14 else None,
        "current_volume": volume_values[-1] if volume_values else None,
        "average_volume_20": average(volume_values[-20:]) if volume_values else None,
        "volume_ratio_20": volume_ratio(candles[-21:]) if len(candles) >= 2 else None,
    }
