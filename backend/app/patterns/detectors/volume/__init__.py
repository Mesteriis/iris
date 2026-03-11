from __future__ import annotations

from typing import Sequence

from app.patterns.base import PatternDetection, PatternDetector
from app.patterns.utils import clamp, closes, pct_change, signal_timestamp, volume_ratio
from app.services.candles_service import CandlePoint


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


def build_volume_detectors() -> list[PatternDetector]:
    return [
        VolumeSpikeDetector(),
        VolumeClimaxDetector(),
        VolumeDivergenceDetector(),
    ]
