from collections.abc import Sequence

from src.apps.anomalies.constants import ANOMALY_TYPE_VOLATILITY_REGIME_BREAK
from src.apps.anomalies.schemas import AnomalyDetectionContext, DetectorFinding
from src.apps.market_data.candles import CandlePoint


def _clamp01(value: float) -> float:
    return max(0.0, min(value, 1.0))


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _average(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return variance ** 0.5


def _scale(value: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    return _clamp01((value - floor) / (ceiling - floor))


def _returns(candles: Sequence[CandlePoint]) -> list[float]:
    result: list[float] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        previous_close = float(previous.close)
        result.append((float(current.close) - previous_close) / previous_close if previous_close else 0.0)
    return result


def _true_ranges(candles: Sequence[CandlePoint]) -> list[float]:
    values: list[float] = []
    previous_close: float | None = None
    for candle in candles:
        high = float(candle.high)
        low = float(candle.low)
        if previous_close is None:
            values.append(high - low)
        else:
            values.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = float(candle.close)
    return values


class VolatilityBreakDetector:
    def __init__(self, *, lookback: int = 48) -> None:
        self._lookback = max(lookback, 24)

    def detect(self, context: AnomalyDetectionContext) -> DetectorFinding | None:
        candles = context.candles[-(self._lookback + 2) :]
        if len(candles) < 20:
            return None

        returns = _returns(candles)
        short_window = returns[-4:]
        long_window = returns[:-4][-24:]
        if len(short_window) < 3 or len(long_window) < 12:
            return None

        short_vol = _stddev(short_window)
        long_vol = _stddev(long_window)
        rolling_vol_ratio = short_vol / long_vol if long_vol > 0 else 0.0

        true_ranges = _true_ranges(candles)
        atr_short = _average(true_ranges[-4:])
        atr_long = _average(true_ranges[:-4][-14:])
        atr_expansion = atr_short / atr_long if atr_long > 0 else 0.0
        realized_ratio = abs(returns[-1]) / long_vol if long_vol > 0 else 0.0

        vol_component = _scale(rolling_vol_ratio, 1.15, 3.2)
        atr_component = _scale(atr_expansion, 1.1, 2.6)
        realized_component = _scale(realized_ratio, 1.2, 4.0)
        volatility_component = (
            (vol_component * 0.45)
            + (atr_component * 0.30)
            + (realized_component * 0.25)
        )
        confirmation_hits = sum(1 for value in returns[-3:] if abs(value) >= max(long_vol * 1.1, 1e-9))

        return DetectorFinding(
            anomaly_type=ANOMALY_TYPE_VOLATILITY_REGIME_BREAK,
            summary=f"{context.symbol} is transitioning into a materially higher volatility regime.",
            component_scores={
                "volatility": _clamp01(volatility_component),
                "price": _clamp01(realized_component * 0.5),
            },
            metrics={
                "rolling_volatility_ratio": float(rolling_vol_ratio),
                "atr_expansion": float(atr_expansion),
                "realized_volatility_ratio": float(realized_ratio),
            },
            confidence=_clamp01((volatility_component * 0.80) + (confirmation_hits / 3.0 * 0.20)),
            explainability={
                "what_happened": f"{context.symbol} moved from a quieter baseline into a higher variance state.",
                "unusualness": "Measured via rolling realized volatility and ATR expansion.",
                "relative_to": "its own recent volatility baseline",
                "relative_to_btc": None,
                "market_wide": False,
            },
            requires_confirmation=True,
            confirmation_hits=confirmation_hits,
            confirmation_target=2,
        )
