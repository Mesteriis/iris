from collections.abc import Sequence

from iris.apps.market_data.candles import CandlePoint
from iris.apps.patterns.domain.base import PatternDetection, PatternDetector
from iris.apps.patterns.domain.utils import clamp, closes, pct_change, signal_timestamp, volume_ratio


class _VolumeDetector(PatternDetector):
    category = "volume"

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


class VolumeSpikeDetector(_VolumeDetector):
    slug = "volume_spike"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        ratio = volume_ratio(candles[-25:])
        if ratio < 2.0:
            return []
        return self._emit(candles, 0.64 + min((ratio - 2) * 0.08, 0.2))


class VolumeClimaxDetector(_VolumeDetector):
    slug = "volume_climax"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 20:
            return []
        ratio = volume_ratio(candles[-25:])
        candle = candles[-1]
        body = abs(float(candle.close) - float(candle.open))
        full_range = max(float(candle.high) - float(candle.low), 1e-9)
        trend_move = abs(pct_change(float(candle.close), float(candles[-10].close)))
        if ratio < 2.5 or body / full_range > 0.4 or trend_move < 0.05:
            return []
        return self._emit(candles, 0.68 + min((ratio - 2.5) * 0.05, 0.15))


class VolumeDivergenceDetector(_VolumeDetector):
    slug = "volume_divergence"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 40:
            return []
        price_values = closes(candles[-40:])
        old_high = max(price_values[-30:-10])
        old_low = min(price_values[-30:-10])
        recent_volume = sum(float(item.volume or 0.0) for item in candles[-10:]) / 10
        previous_volume = sum(float(item.volume or 0.0) for item in candles[-20:-10]) / 10
        if previous_volume <= 0:
            return []
        bearish_divergence = price_values[-1] > old_high and recent_volume < previous_volume * 0.85
        bullish_divergence = price_values[-1] < old_low and recent_volume < previous_volume * 0.85
        if not (bearish_divergence or bullish_divergence):
            return []
        return self._emit(candles, 0.66 + max((previous_volume - recent_volume) / previous_volume, 0) * 0.2)


class VolumeDryUpDetector(_VolumeDetector):
    slug = "volume_dry_up"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 25:
            return []
        ratio = volume_ratio(candles[-25:])
        prices = closes(candles[-25:])
        consolidation = max(prices[-10:-1]) - min(prices[-10:-1])
        if ratio > 0.65 or consolidation / max(prices[-2], 1e-9) > 0.04:
            return []
        if prices[-1] < max(prices[-15:-5]) * 0.98:
            return []
        return self._emit(candles, 0.64 + max(0.65 - ratio, 0))


class VolumeBreakoutConfirmationDetector(_VolumeDetector):
    slug = "volume_breakout_confirmation"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 25:
            return []
        ratio = volume_ratio(candles[-25:])
        prices = closes(candles[-25:])
        if ratio < 1.8 or prices[-1] <= max(prices[-12:-1]):
            return []
        return self._emit(candles, 0.67 + min((ratio - 1.8) * 0.06, 0.18))


class AccumulationDistributionDetector(_VolumeDetector):
    def __init__(self, slug: str, direction: str):
        self.slug = slug
        self.direction = direction

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 20:
            return []
        window = candles[-20:]
        up_flow = sum(float(item.volume or 0.0) for item in window if float(item.close) >= float(item.open))
        down_flow = sum(float(item.volume or 0.0) for item in window if float(item.close) < float(item.open))
        if self.direction == "bull":
            if up_flow <= down_flow * 1.25 or float(window[-1].close) <= float(window[0].close):
                return []
            return self._emit(candles, 0.66 + min((up_flow - down_flow) / max(up_flow, 1e-9), 0.2))
        if down_flow <= up_flow * 1.25 or float(window[-1].close) >= float(window[0].close):
            return []
        return self._emit(candles, 0.66 + min((down_flow - up_flow) / max(down_flow, 1e-9), 0.2))


class ChurnBarDetector(_VolumeDetector):
    slug = "churn_bar"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        ratio = volume_ratio(candles[-20:])
        candle = candles[-1]
        body = abs(float(candle.close) - float(candle.open))
        total_range = max(float(candle.high) - float(candle.low), 1e-9)
        if ratio < 2.2 or body / total_range > 0.25:
            return []
        return self._emit(candles, 0.66 + min((ratio - 2.2) * 0.05, 0.14))


class EffortResultDivergenceDetector(_VolumeDetector):
    def __init__(self, slug: str, direction: str):
        self.slug = slug
        self.direction = direction

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 18:
            return []
        ratio = volume_ratio(candles[-18:])
        last = candles[-1]
        last_return = pct_change(float(last.close), float(last.open))
        if self.direction == "bull":
            if ratio < 1.8 or last_return <= 0 or (float(last.high) - float(last.close)) / max(float(last.close), 1e-9) > 0.02:
                return []
            return self._emit(candles, 0.67 + min(last_return * 4, 0.15))
        if ratio < 1.8 or last_return >= 0 or (float(last.close) - float(last.low)) / max(float(last.close), 1e-9) > 0.02:
            return []
        return self._emit(candles, 0.67 + min(abs(last_return) * 4, 0.15))


class RelativeVolumeBreakoutDetector(_VolumeDetector):
    slug = "relative_volume_breakout"

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 20:
            return []
        ratio = volume_ratio(candles[-20:])
        prices = closes(candles[-20:])
        if ratio < 2.0 or prices[-1] <= max(prices[-8:-1]):
            return []
        return self._emit(candles, 0.67 + min((ratio - 2.0) * 0.06, 0.18))


class VolumeFollowThroughDetector(_VolumeDetector):
    def __init__(self, slug: str, direction: str):
        self.slug = slug
        self.direction = direction

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 12:
            return []
        previous = candles[-2]
        current = candles[-1]
        if self.direction == "bull":
            if not (
                float(previous.close) > float(previous.open)
                and float(current.close) > float(previous.high)
                and volume_ratio(candles[-12:]) > 1.4
            ):
                return []
            return self._emit(candles, 0.66)
        if not (
            float(previous.close) < float(previous.open)
            and float(current.close) < float(previous.low)
            and volume_ratio(candles[-12:]) > 1.4
        ):
            return []
        return self._emit(candles, 0.66)


class ClimaxTurnDetector(_VolumeDetector):
    def __init__(self, slug: str, direction: str):
        self.slug = slug
        self.direction = direction

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 16:
            return []
        ratio = volume_ratio(candles[-16:])
        prices = closes(candles[-16:])
        last = candles[-1]
        trend_move = pct_change(prices[-2], prices[-10])
        if self.direction == "top":
            if ratio < 2.5 or trend_move < 0.06 or float(last.close) >= float(last.open):
                return []
            return self._emit(candles, 0.69 + min((ratio - 2.5) * 0.04, 0.12))
        if ratio < 2.5 or trend_move > -0.06 or float(last.close) <= float(last.open):
            return []
        return self._emit(candles, 0.69 + min((ratio - 2.5) * 0.04, 0.12))


class VolumeTrendConfirmationDetector(_VolumeDetector):
    def __init__(self, slug: str, direction: str):
        self.slug = slug
        self.direction = direction

    def detect(self, candles: Sequence[CandlePoint], indicators: dict[str, float | None]) -> list[PatternDetection]:
        del indicators
        if len(candles) < 25:
            return []
        prices = closes(candles[-25:])
        recent_ratio = volume_ratio(candles[-25:])
        trend = pct_change(prices[-1], prices[-10])
        if self.direction == "bull":
            if recent_ratio < 1.3 or trend <= 0.03:
                return []
            return self._emit(candles, 0.65 + min(trend, 0.2))
        if recent_ratio < 1.3 or trend >= -0.03:
            return []
        return self._emit(candles, 0.65 + min(abs(trend), 0.2))


def build_volume_detectors() -> list[PatternDetector]:
    return [
        VolumeSpikeDetector(),
        VolumeClimaxDetector(),
        VolumeDivergenceDetector(),
        VolumeDryUpDetector(),
        VolumeBreakoutConfirmationDetector(),
        AccumulationDistributionDetector("accumulation_volume", "bull"),
        AccumulationDistributionDetector("distribution_volume", "bear"),
        ChurnBarDetector(),
        EffortResultDivergenceDetector("effort_result_divergence_bullish", "bull"),
        EffortResultDivergenceDetector("effort_result_divergence_bearish", "bear"),
        RelativeVolumeBreakoutDetector(),
        VolumeFollowThroughDetector("volume_follow_through_bullish", "bull"),
        VolumeFollowThroughDetector("volume_follow_through_bearish", "bear"),
        ClimaxTurnDetector("buying_climax", "top"),
        ClimaxTurnDetector("selling_climax", "bottom"),
        VolumeTrendConfirmationDetector("volume_trend_confirmation_bullish", "bull"),
        VolumeTrendConfirmationDetector("volume_trend_confirmation_bearish", "bear"),
    ]
