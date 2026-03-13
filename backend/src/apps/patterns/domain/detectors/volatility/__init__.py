from __future__ import annotations

from typing import Sequence

from src.apps.patterns.domain.base import PatternDetection, PatternDetector
from src.apps.patterns.domain.utils import average, clamp, closes, signal_timestamp, volume_ratio
from src.apps.market_data.candles import CandlePoint
from src.apps.indicators.domain import atr_series, bollinger_bands


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


class VolatilityCompressionDetector(_VolatilityDetector):
    slug = "volatility_compression"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-50:])
        if len(prices) < 25:
            return []
        _, _, _, widths = bollinger_bands(prices, period=20)
        recent = [float(value) for value in widths[-10:] if value is not None]
        prior = [float(value) for value in widths[-30:-10] if value is not None]
        if len(recent) < 5 or len(prior) < 10:
            return []
        if average(recent) >= average(prior) * 0.7:
            return []
        confidence = 0.64 + max((average(prior) - average(recent)) / max(average(prior), 1e-9), 0.0)
        return self._emit(candles, confidence)


class VolatilityExpansionBreakoutDetector(_VolatilityDetector):
    slug = "volatility_expansion_breakout"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-50:])
        if len(prices) < 25:
            return []
        _, _, _, widths = bollinger_bands(prices, period=20)
        current_width = widths[-1]
        baseline = average([float(value) for value in widths[-10:-1] if value is not None])
        price_breakout = prices[-1] > max(prices[-10:-1]) or prices[-1] < min(prices[-10:-1])
        if current_width is None or baseline <= 0 or current_width < baseline * 1.5 or not price_breakout:
            return []
        confidence = 0.65 + min(current_width / baseline / 10, 0.2)
        return self._emit(candles, confidence)


class AtrCompressionDetector(_VolatilityDetector):
    slug = "atr_compression"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-50:])
        highs = [float(item.high) for item in candles[-50:]]
        lows = [float(item.low) for item in candles[-50:]]
        atr_values = atr_series(highs, lows, prices, 14)
        recent = [float(value) for value in atr_values[-10:] if value is not None]
        prior = [float(value) for value in atr_values[-25:-10] if value is not None]
        if len(recent) < 5 or len(prior) < 8:
            return []
        if average(recent) >= average(prior) * 0.75:
            return []
        confidence = 0.64 + max((average(prior) - average(recent)) / max(average(prior), 1e-9), 0.0)
        return self._emit(candles, confidence)


class AtrReleaseDetector(_VolatilityDetector):
    slug = "atr_release"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-50:])
        highs = [float(item.high) for item in candles[-50:]]
        lows = [float(item.low) for item in candles[-50:]]
        atr_values = atr_series(highs, lows, prices, 14)
        recent = [float(value) for value in atr_values[-5:] if value is not None]
        baseline = average([float(value) for value in atr_values[-20:-5] if value is not None])
        if len(recent) < 3 or baseline <= 0 or average(recent) < baseline * 1.4:
            return []
        confidence = 0.65 + min(average(recent) / baseline / 10, 0.2)
        return self._emit(candles, confidence)


class NarrowRangeBreakoutDetector(_VolatilityDetector):
    slug = "narrow_range_breakout"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        window = candles[-12:]
        prices = closes(window)
        if len(prices) < 8:
            return []
        daily_range = max(float(window[-2].high) - float(window[-2].low), 1e-9)
        baseline = average(
            [float(item.high) - float(item.low) for item in candles[-12:-2]]
        )
        if baseline <= 0 or daily_range > baseline * 0.7:
            return []
        if not (prices[-1] > max(prices[:-1]) or prices[-1] < min(prices[:-1])):
            return []
        confidence = 0.66 + max(volume_ratio(candles[-20:]) - 1, 0) * 0.05
        return self._emit(candles, confidence)


class BandWalkDetector(_VolatilityDetector):
    def __init__(self, slug: str, direction: str):
        self.slug = slug
        self.direction = direction

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-40:])
        if len(prices) < 25:
            return []
        upper, _, lower, _ = bollinger_bands(prices, period=20)
        if self.direction == "bull":
            if not all(
                upper[index] is not None and prices[index] >= float(upper[index]) * 0.985
                for index in range(len(prices) - 4, len(prices))
            ):
                return []
            return self._emit(candles, 0.67)
        if not all(
            lower[index] is not None and prices[index] <= float(lower[index]) * 1.015
            for index in range(len(prices) - 4, len(prices))
        ):
            return []
        return self._emit(candles, 0.67)


class MeanReversionSnapDetector(_VolatilityDetector):
    slug = "mean_reversion_snap"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-40:])
        if len(prices) < 25:
            return []
        upper, middle, lower, _ = bollinger_bands(prices, period=20)
        if upper[-2] is None or lower[-2] is None or middle[-1] is None:
            return []
        overshot_upper = prices[-2] > float(upper[-2]) and prices[-1] < float(middle[-1])
        overshot_lower = prices[-2] < float(lower[-2]) and prices[-1] > float(middle[-1])
        if not (overshot_upper or overshot_lower):
            return []
        confidence = 0.65 + max(volume_ratio(candles[-20:]) - 1, 0) * 0.03
        return self._emit(candles, confidence)


class VolatilityReversalDetector(_VolatilityDetector):
    def __init__(self, slug: str, direction: str):
        self.slug = slug
        self.direction = direction

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        prices = closes(candles[-50:])
        if len(prices) < 25:
            return []
        _, _, _, widths = bollinger_bands(prices, period=20)
        recent_width = average([float(value) for value in widths[-6:-1] if value is not None])
        prior_width = average([float(value) for value in widths[-16:-6] if value is not None])
        if prior_width <= 0 or recent_width < prior_width * 1.25:
            return []
        if self.direction == "bull":
            if not (prices[-2] < prices[-3] and prices[-1] > prices[-2]):
                return []
            return self._emit(candles, 0.66)
        if not (prices[-2] > prices[-3] and prices[-1] < prices[-2]):
            return []
        return self._emit(candles, 0.66)


def build_volatility_detectors() -> list[PatternDetector]:
    return [
        BollingerSqueezeDetector(),
        BollingerExpansionDetector(),
        AtrSpikeDetector(),
        VolatilityCompressionDetector(),
        VolatilityExpansionBreakoutDetector(),
        AtrCompressionDetector(),
        AtrReleaseDetector(),
        NarrowRangeBreakoutDetector(),
        BandWalkDetector("band_walk_bullish", "bull"),
        BandWalkDetector("band_walk_bearish", "bear"),
        MeanReversionSnapDetector(),
        VolatilityReversalDetector("volatility_reversal_bullish", "bull"),
        VolatilityReversalDetector("volatility_reversal_bearish", "bear"),
    ]
