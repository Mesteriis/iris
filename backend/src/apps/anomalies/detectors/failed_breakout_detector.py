from collections.abc import Sequence

from src.apps.anomalies.constants import ANOMALY_TYPE_FAILED_BREAKOUT
from src.apps.anomalies.schemas import AnomalyDetectionContext, DetectorFinding
from src.apps.market_data.candles import CandlePoint


def _clamp01(value: float) -> float:
    return max(0.0, min(value, 1.0))


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _scale(value: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    return _clamp01((value - floor) / (ceiling - floor))


def _wick_body_ratio(*, candle: CandlePoint, direction: str) -> float:
    upper_wick = float(candle.high) - max(float(candle.open), float(candle.close))
    lower_wick = min(float(candle.open), float(candle.close)) - float(candle.low)
    body = abs(float(candle.close) - float(candle.open))
    denominator = body if body > 1e-9 else max(float(candle.close) * 0.001, 1e-9)
    wick = upper_wick if direction == "upside" else lower_wick
    return max(wick, 0.0) / denominator


class FailedBreakoutDetector:
    def __init__(self, *, lookback: int = 32, breakout_window: int = 12) -> None:
        self._lookback = max(lookback, 20)
        self._breakout_window = max(breakout_window, 8)

    def detect(self, context: AnomalyDetectionContext) -> DetectorFinding | None:
        candles = context.candles[-(self._lookback + 1) :]
        if len(candles) < self._breakout_window + 1:
            return None

        previous_candles = candles[:-1]
        current = candles[-1]
        local_window = previous_candles[-self._breakout_window :]
        reference_high = max(float(candle.high) for candle in local_window)
        reference_low = min(float(candle.low) for candle in local_window)
        current_high = float(current.high)
        current_low = float(current.low)
        current_close = float(current.close)

        upside_excursion = ((current_high - reference_high) / reference_high) if reference_high > 0 else 0.0
        downside_excursion = ((reference_low - current_low) / reference_low) if reference_low > 0 else 0.0
        upside_rejection = ((reference_high - current_close) / reference_high) if reference_high > 0 else 0.0
        downside_rejection = ((current_close - reference_low) / reference_low) if reference_low > 0 else 0.0

        direction = ""
        breakout_excursion = 0.0
        rejection_depth = 0.0
        reference_level = 0.0
        if upside_excursion >= 0.001 and upside_rejection >= 0.0005:
            direction = "upside"
            breakout_excursion = upside_excursion
            rejection_depth = upside_rejection
            reference_level = reference_high
        if downside_excursion >= 0.001 and downside_rejection >= 0.0005 and downside_excursion + downside_rejection > breakout_excursion + rejection_depth:
            direction = "downside"
            breakout_excursion = downside_excursion
            rejection_depth = downside_rejection
            reference_level = reference_low
        if not direction:
            return None

        volume_values = [
            float(candle.volume)
            for candle in previous_candles[-self._breakout_window :]
            if candle.volume is not None
        ]
        current_volume = float(current.volume) if current.volume is not None else 0.0
        volume_ratio = current_volume / _average(volume_values) if volume_values and _average(volume_values) > 0 else 0.0
        wick_ratio = _wick_body_ratio(candle=current, direction=direction)

        breakout_component = _scale(breakout_excursion, 0.001, 0.025)
        rejection_component = _scale(rejection_depth, 0.0007, 0.015)
        wick_component = _scale(wick_ratio, 0.9, 5.0)
        volume_component = _scale(volume_ratio, 1.0, 3.5)
        price_component = (
            (rejection_component * 0.42)
            + (breakout_component * 0.23)
            + (wick_component * 0.25)
            + (volume_component * 0.10)
        )
        if price_component < 0.42:
            return None

        rejected_level = "high" if direction == "upside" else "low"
        return DetectorFinding(
            anomaly_type=ANOMALY_TYPE_FAILED_BREAKOUT,
            summary=(
                f"{context.symbol} attempted a {direction} breakout through the rolling {rejected_level} "
                "and then closed back inside the prior range."
            ),
            component_scores={
                "price": _clamp01(price_component),
                "volatility": _clamp01((breakout_component * 0.45) + (wick_component * 0.55)),
            },
            metrics={
                "breakout_excursion": float(breakout_excursion),
                "rejection_depth": float(rejection_depth),
                "wick_body_ratio": float(wick_ratio),
                "volume_ratio": float(volume_ratio),
                "reference_level": float(reference_level),
            },
            confidence=_clamp01((price_component * 0.75) + (wick_component * 0.25)),
            explainability={
                "what_happened": f"{context.symbol} broke a local range level intrabar and then failed to hold it by the close.",
                "unusualness": "Measured via breakout excursion, rejection depth, wick-to-body ratio and confirmation volume.",
                "relative_to": f"the rolling {self._breakout_window}-candle breakout level",
                "relative_to_btc": None,
                "market_wide": False,
            },
        )
