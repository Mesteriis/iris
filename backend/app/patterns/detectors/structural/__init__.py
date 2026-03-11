from __future__ import annotations

from typing import Sequence

from app.patterns.base import PatternDetection, PatternDetector
from app.patterns.utils import (
    clamp,
    closes,
    find_pivots,
    highs,
    linear_slope,
    lows,
    pct_change,
    signal_timestamp,
    within_tolerance,
)
from app.services.candles_service import CandlePoint


class _StructuralDetector(PatternDetector):
    category = "structural"

    def _emit(self, candles: Sequence[CandlePoint], confidence: float) -> list[PatternDetection]:
        return [
            PatternDetection(
                slug=self.slug,
                signal_type=f"pattern_{self.slug}",
                confidence=clamp(confidence, 0.55, 0.95),
                candle_timestamp=signal_timestamp(candles),
                category=self.category,
            )
        ]


class HeadShouldersDetector(_StructuralDetector):
    slug = "head_shoulders"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 40:
            return []
        pivot_highs = find_pivots(closes(candles[-90:]), kind="high")
        pivot_lows = find_pivots(closes(candles[-90:]), kind="low")
        if len(pivot_highs) < 3 or len(pivot_lows) < 2:
            return []
        left, head, right = pivot_highs[-3:]
        if not (head.price > left.price * 1.02 and head.price > right.price * 1.02):
            return []
        if not within_tolerance(left.price, right.price, 0.035):
            return []
        neckline_points = [pivot.price for pivot in pivot_lows if left.index < pivot.index < right.index]
        if len(neckline_points) < 2:
            return []
        neckline = sum(neckline_points[-2:]) / 2
        latest = float(candles[-1].close)
        if latest > neckline:
            return []
        confidence = 0.68 + (min(left.price, right.price) / head.price - 0.75) * 0.4
        return self._emit(candles, confidence)


class InverseHeadShouldersDetector(_StructuralDetector):
    slug = "inverse_head_shoulders"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 40:
            return []
        pivot_lows = find_pivots(closes(candles[-90:]), kind="low")
        pivot_highs = find_pivots(closes(candles[-90:]), kind="high")
        if len(pivot_lows) < 3 or len(pivot_highs) < 2:
            return []
        left, head, right = pivot_lows[-3:]
        if not (head.price < left.price * 0.98 and head.price < right.price * 0.98):
            return []
        if not within_tolerance(left.price, right.price, 0.035):
            return []
        neckline_points = [pivot.price for pivot in pivot_highs if left.index < pivot.index < right.index]
        if len(neckline_points) < 2:
            return []
        neckline = sum(neckline_points[-2:]) / 2
        latest = float(candles[-1].close)
        if latest < neckline:
            return []
        confidence = 0.68 + (1 - head.price / max(left.price, right.price)) * 0.8
        return self._emit(candles, confidence)


class MultiTopBottomDetector(_StructuralDetector):
    def __init__(self, *, slug: str, direction: str, touches: int):
        self.slug = slug
        self.direction = direction
        self.touches = touches

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 30:
            return []
        prices = closes(candles[-90:])
        pivot_kind = "high" if self.direction == "top" else "low"
        pivots = find_pivots(prices, kind=pivot_kind)
        if len(pivots) < self.touches:
            return []
        selected = pivots[-self.touches :]
        reference = sum(pivot.price for pivot in selected) / len(selected)
        if not all(within_tolerance(pivot.price, reference, 0.025) for pivot in selected):
            return []
        support = min(prices[selected[0].index : selected[-1].index + 1])
        resistance = max(prices[selected[0].index : selected[-1].index + 1])
        latest = prices[-1]
        if self.direction == "top" and latest > support:
            return []
        if self.direction == "bottom" and latest < resistance:
            return []
        pattern_depth = abs(resistance - support) / max(reference, 1e-9)
        confidence = 0.62 + pattern_depth * 1.8 + (self.touches - 2) * 0.04
        return self._emit(candles, confidence)


class TriangleDetector(_StructuralDetector):
    def __init__(self, slug: str):
        self.slug = slug

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 35:
            return []
        window = candles[-60:]
        price_highs = highs(window)
        price_lows = lows(window)
        highs_pivots = find_pivots(price_highs, kind="high")
        lows_pivots = find_pivots(price_lows, kind="low")
        if len(highs_pivots) < 3 or len(lows_pivots) < 3:
            return []
        recent_highs = [pivot.price for pivot in highs_pivots[-3:]]
        recent_lows = [pivot.price for pivot in lows_pivots[-3:]]
        high_slope = linear_slope(recent_highs)
        low_slope = linear_slope(recent_lows)
        close_price = float(window[-1].close)
        resistance = max(recent_highs)
        support = min(recent_lows)
        compressed = (resistance - support) / max(close_price, 1e-9) < 0.08
        if not compressed:
            return []
        if self.slug == "ascending_triangle":
            if not (abs(high_slope) < close_price * 0.002 and low_slope > 0):
                return []
            if close_price < resistance:
                return []
            confidence = 0.68 + pct_change(close_price, support) * 0.8
            return self._emit(candles, confidence)
        if self.slug == "descending_triangle":
            if not (abs(low_slope) < close_price * 0.002 and high_slope < 0):
                return []
            if close_price > support:
                return []
            confidence = 0.68 + abs(pct_change(close_price, resistance)) * 0.8
            return self._emit(candles, confidence)
        if not (high_slope < 0 and low_slope > 0):
            return []
        breakout = close_price > resistance or close_price < support
        if not breakout:
            return []
        confidence = 0.66 + abs(high_slope - low_slope) / max(close_price, 1e-9) * 5
        return self._emit(candles, confidence)


class WedgeDetector(_StructuralDetector):
    def __init__(self, slug: str):
        self.slug = slug

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 30:
            return []
        window = candles[-45:]
        high_slice = highs(window)
        low_slice = lows(window)
        high_slope = linear_slope(high_slice[-15:])
        low_slope = linear_slope(low_slice[-15:])
        price = float(window[-1].close)
        range_start = max(high_slice[:15]) - min(low_slice[:15])
        range_end = max(high_slice[-15:]) - min(low_slice[-15:])
        if range_start <= 0 or range_end >= range_start:
            return []
        if self.slug == "rising_wedge":
            if not (high_slope > 0 and low_slope > 0 and low_slope > high_slope):
                return []
            if price > min(low_slice[-5:]):
                return []
            confidence = 0.64 + (range_start - range_end) / range_start
            return self._emit(candles, confidence)
        if not (high_slope < 0 and low_slope < 0 and high_slope < low_slope):
            return []
        if price < max(high_slice[-5:]):
            return []
        confidence = 0.64 + (range_start - range_end) / range_start
        return self._emit(candles, confidence)


def build_structural_detectors() -> list[PatternDetector]:
    return [
        HeadShouldersDetector(),
        InverseHeadShouldersDetector(),
        MultiTopBottomDetector(slug="double_top", direction="top", touches=2),
        MultiTopBottomDetector(slug="double_bottom", direction="bottom", touches=2),
        MultiTopBottomDetector(slug="triple_top", direction="top", touches=3),
        MultiTopBottomDetector(slug="triple_bottom", direction="bottom", touches=3),
        TriangleDetector("ascending_triangle"),
        TriangleDetector("descending_triangle"),
        TriangleDetector("symmetrical_triangle"),
        WedgeDetector("rising_wedge"),
        WedgeDetector("falling_wedge"),
    ]
