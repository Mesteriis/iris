from __future__ import annotations

from typing import Sequence

from app.patterns.base import PatternDetection, PatternDetector
from app.patterns.utils import average, clamp, closes, signal_timestamp, volume_ratio
from app.services.candles_service import CandlePoint
from app.services.indicator_engine import atr_series, bollinger_bands


class _VolatilityDetector(PatternDetector):
    category = "volatility"

    def _emit(self, candles: Sequence[CandlePoint], confidence: float) -> list[PatternDetection]:
        return [
            PatternDetection(
                slug=self.slug,
                signal_type=f"pattern_{self.slug}",
                confidence=clamp(confidence, 0.55, 0.9),
                candle_timestamp=signal_timestamp(candles),
                category=self.category,
            )
        ]


class BollingerSqueezeDetector(_VolatilityDetector):
    slug = "bollinger_squeeze"
    required_indicators = ["bb_width"]

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-60:])
        if len(prices) < 25:
            return []
        _, _, _, widths = bollinger_bands(prices, period=20)
        current_width = widths[-1]
        past_widths = [value for value in widths[-30:-1] if value is not None]
        if current_width is None or len(past_widths) < 10:
            return []
        if current_width >= min(sorted(past_widths)[: max(len(past_widths) // 5, 1)]):
            return []
        breakout = abs(prices[-1] - prices[-2]) / max(prices[-2], 1e-9) > 0.015
        if not breakout:
            return []
        confidence = 0.66 + max(volume_ratio(candles[-20:]) - 1, 0) * 0.06
        return self._emit(candles, confidence)


class BollingerExpansionDetector(_VolatilityDetector):
    slug = "bollinger_expansion"
    required_indicators = ["bb_width"]

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-60:])
        if len(prices) < 25:
            return []
        _, _, _, widths = bollinger_bands(prices, period=20)
        current_width = widths[-1]
        previous_widths = [value for value in widths[-10:-1] if value is not None]
        if current_width is None or len(previous_widths) < 5:
            return []
        baseline = average([float(value) for value in previous_widths])
        if baseline <= 0 or current_width < baseline * 1.4:
            return []
        confidence = 0.64 + min(current_width / baseline / 10, 0.2)
        return self._emit(candles, confidence)


class AtrSpikeDetector(_VolatilityDetector):
    slug = "atr_spike"
    required_indicators = ["atr_14"]

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-60:])
        highs = [float(item.high) for item in candles[-60:]]
        lows = [float(item.low) for item in candles[-60:]]
        atr_values = atr_series(highs, lows, prices, 14)
        current_atr = atr_values[-1]
        baseline = average([float(value) for value in atr_values[-20:-1] if value is not None])
        if current_atr is None or baseline <= 0 or current_atr < baseline * 1.5:
            return []
        confidence = 0.64 + min(current_atr / baseline / 10, 0.2)
        return self._emit(candles, confidence)


def build_volatility_detectors() -> list[PatternDetector]:
    return [
        BollingerSqueezeDetector(),
        BollingerExpansionDetector(),
        AtrSpikeDetector(),
    ]
