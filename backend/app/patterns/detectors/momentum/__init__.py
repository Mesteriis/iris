from __future__ import annotations

from typing import Sequence

from app.patterns.base import PatternDetection, PatternDetector
from app.patterns.utils import clamp, closes, find_pivots, signal_timestamp, volume_ratio
from app.services.candles_service import CandlePoint
from app.services.indicator_engine import macd_series, rsi_series


class _MomentumDetector(PatternDetector):
    category = "momentum"

    def _emit(self, candles: Sequence[CandlePoint], confidence: float) -> list[PatternDetection]:
        return [
            PatternDetection(
                slug=self.slug,
                signal_type=f"pattern_{self.slug}",
                confidence=clamp(confidence, 0.55, 0.94),
                candle_timestamp=signal_timestamp(candles),
                category=self.category,
            )
        ]


class RsiDivergenceDetector(_MomentumDetector):
    slug = "rsi_divergence"
    required_indicators = ["rsi_14"]

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-80:])
        if len(prices) < 30:
            return []
        rsi_values = rsi_series(prices, 14)
        pivot_lows = find_pivots(prices, kind="low")
        pivot_highs = find_pivots(prices, kind="high")
        if len(pivot_lows) >= 2:
            left, right = pivot_lows[-2:]
            left_rsi = rsi_values[left.index]
            right_rsi = rsi_values[right.index]
            if (
                left_rsi is not None
                and right_rsi is not None
                and right.price < left.price
                and right_rsi > left_rsi
                and prices[-1] > prices[-2]
            ):
                confidence = 0.67 + min((right_rsi - left_rsi) / 100, 0.2)
                return self._emit(candles, confidence)
        if len(pivot_highs) >= 2:
            left, right = pivot_highs[-2:]
            left_rsi = rsi_values[left.index]
            right_rsi = rsi_values[right.index]
            if (
                left_rsi is not None
                and right_rsi is not None
                and right.price > left.price
                and right_rsi < left_rsi
                and prices[-1] < prices[-2]
            ):
                confidence = 0.67 + min((left_rsi - right_rsi) / 100, 0.2)
                return self._emit(candles, confidence)
        return []


class MacdCrossDetector(_MomentumDetector):
    slug = "macd_cross"
    required_indicators = ["macd", "macd_signal"]

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-60:])
        if len(prices) < 35:
            return []
        macd_line, signal_line, _ = macd_series(prices)
        if len(macd_line) < 2 or macd_line[-1] is None or signal_line[-1] is None:
            return []
        prev_macd = macd_line[-2]
        prev_signal = signal_line[-2]
        if prev_macd is None or prev_signal is None:
            return []
        crossed = (prev_macd <= prev_signal < macd_line[-1]) or (prev_macd >= prev_signal > macd_line[-1])
        if not crossed:
            return []
        confidence = 0.62 + min(abs(macd_line[-1] - signal_line[-1]) * 5, 0.2)
        return self._emit(candles, confidence)


class MacdDivergenceDetector(_MomentumDetector):
    slug = "macd_divergence"
    required_indicators = ["macd_histogram"]

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-80:])
        if len(prices) < 35:
            return []
        _, _, histogram = macd_series(prices)
        pivot_lows = find_pivots(prices, kind="low")
        pivot_highs = find_pivots(prices, kind="high")
        if len(pivot_lows) >= 2:
            left, right = pivot_lows[-2:]
            left_hist = histogram[left.index]
            right_hist = histogram[right.index]
            if left_hist is not None and right_hist is not None and right.price < left.price and right_hist > left_hist:
                return self._emit(candles, 0.69)
        if len(pivot_highs) >= 2:
            left, right = pivot_highs[-2:]
            left_hist = histogram[left.index]
            right_hist = histogram[right.index]
            if left_hist is not None and right_hist is not None and right.price > left.price and right_hist < left_hist:
                return self._emit(candles, 0.69)
        return []


class MomentumExhaustionDetector(_MomentumDetector):
    slug = "momentum_exhaustion"
    required_indicators = ["rsi_14", "macd_histogram"]

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-50:])
        if len(prices) < 30:
            return []
        rsi_values = rsi_series(prices, 14)
        _, _, histogram = macd_series(prices)
        current_rsi = rsi_values[-1]
        previous_hist = histogram[-4:-1]
        current_hist = histogram[-1]
        if current_rsi is None or current_hist is None or any(item is None for item in previous_hist):
            return []
        if current_rsi > 75 and current_hist < max(float(item) for item in previous_hist):
            return self._emit(candles, 0.7 + max(volume_ratio(candles[-20:]) - 1, 0) * 0.04)
        if current_rsi < 25 and current_hist > min(float(item) for item in previous_hist):
            return self._emit(candles, 0.7 + max(volume_ratio(candles[-20:]) - 1, 0) * 0.04)
        return []


def build_momentum_detectors() -> list[PatternDetector]:
    return [
        RsiDivergenceDetector(),
        MacdCrossDetector(),
        MacdDivergenceDetector(),
        MomentumExhaustionDetector(),
    ]
