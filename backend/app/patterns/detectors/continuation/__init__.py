from __future__ import annotations

from typing import Sequence

from app.patterns.base import PatternDetection, PatternDetector
from app.patterns.utils import clamp, closes, highs, linear_slope, lows, pct_change, signal_timestamp, volume_ratio, window_range
from app.services.candles_service import CandlePoint


class _ContinuationDetector(PatternDetector):
    category = "continuation"

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


class FlagDetector(_ContinuationDetector):
    def __init__(self, slug: str, direction: str):
        self.slug = slug
        self.direction = direction

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 30:
            return []
        window = candles[-35:]
        prices = closes(window)
        pole = pct_change(prices[-12], prices[-25])
        pullback = pct_change(prices[-1], prices[-12])
        channel_slope = linear_slope(prices[-10:])
        if self.direction == "bull":
            if not (pole > 0.05 and pullback < 0 and abs(pullback) < abs(pole) * 0.5 and channel_slope < 0):
                return []
            if prices[-1] < max(prices[-5:]):
                return []
            confidence = 0.68 + pole + volume_ratio(window) * 0.05
            return self._emit(candles, confidence)
        if not (pole < -0.05 and pullback > 0 and abs(pullback) < abs(pole) * 0.5 and channel_slope > 0):
            return []
        if prices[-1] > min(prices[-5:]):
            return []
        confidence = 0.68 + abs(pole) + volume_ratio(window) * 0.05
        return self._emit(candles, confidence)


class PennantDetector(_ContinuationDetector):
    slug = "pennant"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 28:
            return []
        window = candles[-30:]
        prices = closes(window)
        pole_move = abs(pct_change(prices[-12], prices[-25]))
        consolidation_range = window_range(prices[-10:]) / max(prices[-10], 1e-9)
        high_slope = linear_slope(highs(window[-10:]))
        low_slope = linear_slope(lows(window[-10:]))
        breakout = abs(pct_change(prices[-1], prices[-4])) > 0.02
        if pole_move < 0.05 or consolidation_range > 0.05 or not (high_slope < 0 < low_slope) or not breakout:
            return []
        confidence = 0.67 + pole_move + max(volume_ratio(window) - 1, 0) * 0.04
        return self._emit(candles, confidence)


class CupAndHandleDetector(_ContinuationDetector):
    slug = "cup_and_handle"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 60:
            return []
        window = candles[-80:]
        prices = closes(window)
        left_rim = max(prices[:20])
        right_rim = max(prices[-20:])
        trough = min(prices[20:-20])
        if not (left_rim > trough * 1.08 and right_rim > trough * 1.08):
            return []
        if abs(left_rim - right_rim) / max(left_rim, 1e-9) > 0.04:
            return []
        handle_low = min(prices[-12:])
        cup_depth = left_rim - trough
        if left_rim - handle_low > cup_depth * 0.4:
            return []
        if prices[-1] < right_rim:
            return []
        confidence = 0.7 + cup_depth / max(left_rim, 1e-9)
        return self._emit(candles, confidence)


class BreakoutRetestDetector(_ContinuationDetector):
    slug = "breakout_retest"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 30:
            return []
        prices = closes(candles[-40:])
        resistance = max(prices[-25:-6])
        support = min(prices[-25:-6])
        breakout_bar = max(prices[-6:-3])
        retest_low = min(prices[-3:])
        last = prices[-1]
        bullish = breakout_bar > resistance and retest_low >= resistance * 0.985 and last >= resistance
        bearish = breakout_bar < support and retest_low <= support * 1.015 and last <= support
        if not (bullish or bearish):
            return []
        confidence = 0.66 + max(volume_ratio(candles[-20:]) - 1, 0) * 0.05
        return self._emit(candles, confidence)


class ConsolidationBreakoutDetector(_ContinuationDetector):
    slug = "consolidation_breakout"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 24:
            return []
        window = candles[-24:]
        prices = closes(window)
        tight_range = window_range(prices[:-1]) / max(prices[-2], 1e-9)
        range_high = max(prices[:-1])
        range_low = min(prices[:-1])
        last = prices[-1]
        if tight_range > 0.06:
            return []
        if not (last > range_high or last < range_low):
            return []
        confidence = 0.65 + max(volume_ratio(window) - 1, 0) * 0.08 + abs(pct_change(last, prices[-2])) * 0.6
        return self._emit(candles, confidence)


def build_continuation_detectors() -> list[PatternDetector]:
    return [
        FlagDetector("bull_flag", "bull"),
        FlagDetector("bear_flag", "bear"),
        PennantDetector(),
        CupAndHandleDetector(),
        BreakoutRetestDetector(),
        ConsolidationBreakoutDetector(),
    ]
