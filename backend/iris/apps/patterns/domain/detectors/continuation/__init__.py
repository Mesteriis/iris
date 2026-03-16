from collections.abc import Sequence

from iris.apps.market_data.candles import CandlePoint
from iris.apps.patterns.domain.base import PatternDetection, PatternDetector
from iris.apps.patterns.domain.utils import (
    clamp,
    closes,
    highs,
    linear_slope,
    lows,
    pct_change,
    signal_timestamp,
    volume_ratio,
    window_range,
)


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


class HighTightFlagDetector(_ContinuationDetector):
    slug = "high_tight_flag"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 30:
            return []
        window = candles[-32:]
        prices = closes(window)
        pole = pct_change(prices[-12], prices[-28])
        consolidation_high = max(prices[-12:-1])
        consolidation_low = min(prices[-12:-1])
        contraction = (consolidation_high - consolidation_low) / max(consolidation_high, 1e-9)
        if pole < 0.1 or contraction > 0.06 or prices[-1] <= consolidation_high:
            return []
        confidence = 0.72 + pole * 0.6 + max(volume_ratio(window) - 1, 0) * 0.04
        return self._emit(candles, confidence)


class ChannelContinuationDetector(_ContinuationDetector):
    def __init__(self, slug: str, direction: str):
        self.slug = slug
        self.direction = direction

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 35:
            return []
        window = candles[-45:]
        price_highs = highs(window)
        price_lows = lows(window)
        high_slope = linear_slope(price_highs[-16:])
        low_slope = linear_slope(price_lows[-16:])
        latest = float(window[-1].close)
        if self.direction == "bull":
            if not (high_slope < 0 and low_slope < 0 and latest > max(price_highs[-10:-1])):
                return []
            confidence = 0.66 + abs(high_slope) / max(latest, 1e-9) * 6
            return self._emit(candles, confidence)
        if not (high_slope > 0 and low_slope > 0 and latest < min(price_lows[-10:-1])):
            return []
        confidence = 0.66 + abs(low_slope) / max(latest, 1e-9) * 6
        return self._emit(candles, confidence)


class MeasuredMoveDetector(_ContinuationDetector):
    def __init__(self, slug: str, direction: str):
        self.slug = slug
        self.direction = direction

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 36:
            return []
        prices = closes(candles[-40:])
        leg_one = pct_change(prices[-24], prices[-36])
        retrace = pct_change(prices[-12], prices[-24])
        leg_two = pct_change(prices[-1], prices[-12])
        if self.direction == "bull":
            if not (leg_one > 0.04 and retrace < 0 and abs(retrace) < abs(leg_one) * 0.7 and leg_two > 0.03):
                return []
            confidence = 0.67 + min(abs(leg_two - leg_one), abs(leg_one)) + max(volume_ratio(candles[-20:]) - 1, 0) * 0.03
            return self._emit(candles, confidence)
        if not (leg_one < -0.04 and retrace > 0 and abs(retrace) < abs(leg_one) * 0.7 and leg_two < -0.03):
            return []
        confidence = 0.67 + min(abs(leg_two - leg_one), abs(leg_one)) + max(volume_ratio(candles[-20:]) - 1, 0) * 0.03
        return self._emit(candles, confidence)


class BaseBreakoutDetector(_ContinuationDetector):
    slug = "base_breakout"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 30:
            return []
        window = candles[-34:]
        prices = closes(window)
        advance = pct_change(prices[-15], prices[0])
        base_high = max(prices[-15:-1])
        base_low = min(prices[-15:-1])
        if advance < 0.05:
            return []
        if (base_high - base_low) / max(base_high, 1e-9) > 0.05 or prices[-1] <= base_high:
            return []
        confidence = 0.68 + advance + max(volume_ratio(window) - 1, 0) * 0.05
        return self._emit(candles, confidence)


class VolatilityContractionBreakDetector(_ContinuationDetector):
    def __init__(self, slug: str, direction: str):
        self.slug = slug
        self.direction = direction

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 32:
            return []
        prices = closes(candles[-36:])
        early_range = window_range(prices[-24:-12]) / max(prices[-13], 1e-9)
        late_range = window_range(prices[-12:-1]) / max(prices[-2], 1e-9)
        if late_range >= early_range * 0.75:
            return []
        range_high = max(prices[-12:-1])
        range_low = min(prices[-12:-1])
        if self.direction == "bull":
            if prices[-1] <= range_high:
                return []
            confidence = 0.67 + max(early_range - late_range, 0)
            return self._emit(candles, confidence)
        if prices[-1] >= range_low:
            return []
        confidence = 0.67 + max(early_range - late_range, 0)
        return self._emit(candles, confidence)


class PullbackContinuationDetector(_ContinuationDetector):
    def __init__(self, slug: str, direction: str):
        self.slug = slug
        self.direction = direction

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 28:
            return []
        prices = closes(candles[-30:])
        trend_leg = pct_change(prices[-10], prices[-24])
        retrace = pct_change(prices[-4], prices[-10])
        resumption = pct_change(prices[-1], prices[-4])
        if self.direction == "bull":
            if not (trend_leg > 0.04 and retrace < 0 and abs(retrace) < abs(trend_leg) * 0.5 and resumption > 0.015):
                return []
            confidence = 0.66 + trend_leg + resumption
            return self._emit(candles, confidence)
        if not (trend_leg < -0.04 and retrace > 0 and abs(retrace) < abs(trend_leg) * 0.5 and resumption < -0.015):
            return []
        confidence = 0.66 + abs(trend_leg) + abs(resumption)
        return self._emit(candles, confidence)


class SqueezeBreakoutDetector(_ContinuationDetector):
    slug = "squeeze_breakout"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 25:
            return []
        window = candles[-25:]
        prices = closes(window)
        pre_range = window_range(prices[-12:-1]) / max(prices[-2], 1e-9)
        if pre_range > 0.04:
            return []
        if prices[-1] <= max(prices[-12:-1]):
            return []
        confidence = 0.67 + max(volume_ratio(window) - 1, 0) * 0.08
        return self._emit(candles, confidence)


class TrendPauseBreakoutDetector(_ContinuationDetector):
    slug = "trend_pause_breakout"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 26:
            return []
        prices = closes(candles[-28:])
        advance = pct_change(prices[-8], prices[0])
        pause_range = window_range(prices[-8:-1]) / max(prices[-2], 1e-9)
        if advance < 0.05 or pause_range > 0.04 or prices[-1] <= max(prices[-8:-1]):
            return []
        confidence = 0.66 + advance
        return self._emit(candles, confidence)


class HandleBreakoutDetector(_ContinuationDetector):
    slug = "handle_breakout"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 45:
            return []
        window = candles[-50:]
        prices = closes(window)
        cup_high = max(prices[:-10])
        handle_low = min(prices[-10:-1])
        if handle_low < cup_high * 0.92:
            return []
        if prices[-1] <= cup_high:
            return []
        confidence = 0.68 + max(volume_ratio(window) - 1, 0) * 0.05
        return self._emit(candles, confidence)


class StairStepContinuationDetector(_ContinuationDetector):
    slug = "stair_step_continuation"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 30:
            return []
        prices = closes(candles[-30:])
        step_one = prices[-20] < prices[-14] < prices[-8]
        pullbacks_hold = min(prices[-17:-14]) > prices[-22] and min(prices[-11:-8]) > prices[-16]
        if not (step_one and pullbacks_hold and prices[-1] > max(prices[-8:-1])):
            return []
        confidence = 0.67 + max(volume_ratio(candles[-20:]) - 1, 0) * 0.05
        return self._emit(candles, confidence)


def build_continuation_detectors() -> list[PatternDetector]:
    return [
        FlagDetector("bull_flag", "bull"),
        FlagDetector("bear_flag", "bear"),
        PennantDetector(),
        CupAndHandleDetector(),
        BreakoutRetestDetector(),
        ConsolidationBreakoutDetector(),
        HighTightFlagDetector(),
        ChannelContinuationDetector("falling_channel_breakout", "bull"),
        ChannelContinuationDetector("rising_channel_breakdown", "bear"),
        MeasuredMoveDetector("measured_move_bullish", "bull"),
        MeasuredMoveDetector("measured_move_bearish", "bear"),
        BaseBreakoutDetector(),
        VolatilityContractionBreakDetector("volatility_contraction_breakout", "bull"),
        VolatilityContractionBreakDetector("volatility_contraction_breakdown", "bear"),
        PullbackContinuationDetector("pullback_continuation_bullish", "bull"),
        PullbackContinuationDetector("pullback_continuation_bearish", "bear"),
        SqueezeBreakoutDetector(),
        TrendPauseBreakoutDetector(),
        HandleBreakoutDetector(),
        StairStepContinuationDetector(),
    ]
