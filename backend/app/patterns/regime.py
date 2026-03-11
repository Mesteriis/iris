from __future__ import annotations

from dataclasses import dataclass

from app.patterns.utils import current_indicator_map
from app.services.candles_service import fetch_candle_points

MARKET_REGIMES = [
    "bull_trend",
    "bear_trend",
    "sideways_range",
    "high_volatility",
    "low_volatility",
]


@dataclass(slots=True, frozen=True)
class RegimeRead:
    timeframe: int
    regime: str
    confidence: float


def detect_market_regime(indicators: dict[str, float | None], volatility: float | None = None) -> tuple[str, float]:
    price = float(indicators.get("price_current") or 0.0)
    ema_20 = indicators.get("ema_20")
    ema_50 = indicators.get("ema_50")
    sma_200 = indicators.get("sma_200")
    macd_hist = indicators.get("macd_histogram")
    adx = indicators.get("adx_14")
    bb_width = indicators.get("bb_width")
    atr = indicators.get("atr_14")

    if (
        price > float(sma_200 or 0)
        and ema_20 is not None
        and ema_50 is not None
        and ema_20 > ema_50
        and (macd_hist or 0) > 0
        and (adx or 0) >= 20
    ):
        return "bull_trend", min(0.6 + ((adx or 20) / 100), 0.95)
    if (
        sma_200 is not None
        and price < sma_200
        and ema_20 is not None
        and ema_50 is not None
        and ema_20 < ema_50
        and (macd_hist or 0) < 0
        and (adx or 0) >= 20
    ):
        return "bear_trend", min(0.6 + ((adx or 20) / 100), 0.95)

    atr_ratio = (float(atr or 0.0) / price) if price > 0 else 0.0
    if (bb_width or 0) >= 0.1 or atr_ratio >= 0.03 or (volatility or 0) > price * 0.04:
        return "high_volatility", 0.72
    if (bb_width or 0) <= 0.04 and (adx or 0) < 18:
        return "low_volatility", 0.7
    return "sideways_range", 0.65


def calculate_regime_map(
    snapshots: dict[int, object],
    *,
    volatility: float | None,
) -> dict[int, RegimeRead]:
    regimes: dict[int, RegimeRead] = {}
    for timeframe, snapshot in snapshots.items():
        indicators = {
            "price_current": getattr(snapshot, "price_current", None),
            "ema_20": getattr(snapshot, "ema_20", None),
            "ema_50": getattr(snapshot, "ema_50", None),
            "sma_200": getattr(snapshot, "sma_200", None),
            "macd_histogram": getattr(snapshot, "macd_histogram", None),
            "adx_14": getattr(snapshot, "adx_14", None),
            "bb_width": getattr(snapshot, "bb_width", None),
            "atr_14": getattr(snapshot, "atr_14", None),
        }
        regime, confidence = detect_market_regime(indicators, volatility)
        regimes[timeframe] = RegimeRead(timeframe=timeframe, regime=regime, confidence=confidence)
    return regimes


def primary_regime(regimes: dict[int, RegimeRead]) -> str | None:
    for timeframe in (1440, 240, 60, 15):
        if timeframe in regimes:
            return regimes[timeframe].regime
    return None


def compute_live_regimes(db, coin_id: int) -> list[RegimeRead]:
    rows: list[RegimeRead] = []
    for timeframe in (15, 60, 240, 1440):
        candles = fetch_candle_points(db, coin_id, timeframe, 200)
        if len(candles) < 20:
            continue
        indicators = current_indicator_map(candles)
        regime, confidence = detect_market_regime(indicators)
        rows.append(RegimeRead(timeframe=timeframe, regime=regime, confidence=confidence))
    return rows
