from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    ema_50 = indicators.get("ema_50")
    ema_200 = indicators.get("ema_200")
    sma_200 = indicators.get("sma_200")
    adx = indicators.get("adx_14")
    price_change_7d = float(indicators.get("price_change_7d") or 0.0)
    bb_width = indicators.get("bb_width")
    prev_bb_width = indicators.get("prev_bb_width")
    atr = indicators.get("atr_14")
    prev_atr = indicators.get("prev_atr_14")
    reference_average = ema_200 if ema_200 is not None else sma_200

    atr_ratio = (float(atr or 0.0) / price) if price > 0 else 0.0
    atr_rising = (
        atr is not None
        and prev_atr is not None
        and float(atr) > float(prev_atr) * 1.03
    )
    bb_expanding = (
        bb_width is not None
        and prev_bb_width is not None
        and float(bb_width) > float(prev_bb_width) * 1.05
    )
    bb_narrow = bb_width is not None and float(bb_width) <= 0.04
    low_atr = atr_ratio <= 0.015

    if reference_average is not None and ema_50 is not None and (adx or 0) > 25:
        if ema_50 > reference_average and price_change_7d >= 0:
            return "bull_trend", min(0.65 + min((adx or 25) / 120, 0.22), 0.95)
        if ema_50 < reference_average and price_change_7d <= 0:
            return "bear_trend", min(0.65 + min((adx or 25) / 120, 0.22), 0.95)

    if atr_rising and bb_expanding:
        return "high_volatility", 0.8
    if low_atr and bb_narrow:
        return "low_volatility", 0.78
    if (adx or 0) < 20:
        return "sideways_range", 0.72
    if atr_ratio >= 0.03 and (bb_width or 0) >= 0.08:
        return "high_volatility", 0.74
    return "sideways_range", 0.65


def calculate_regime_map(
    snapshots: dict[int, object],
    *,
    volatility: float | None,
    price_change_7d: float | None = None,
) -> dict[int, RegimeRead]:
    regimes: dict[int, RegimeRead] = {}
    for timeframe, snapshot in snapshots.items():
        indicators = {
            "price_current": getattr(snapshot, "price_current", None),
            "ema_50": getattr(snapshot, "ema_50", None),
            "ema_200": getattr(snapshot, "ema_200", None),
            "sma_200": getattr(snapshot, "sma_200", None),
            "adx_14": getattr(snapshot, "adx_14", None),
            "bb_width": getattr(snapshot, "bb_width", None),
            "prev_bb_width": getattr(snapshot, "prev_bb_width", None),
            "atr_14": getattr(snapshot, "atr_14", None),
            "prev_atr_14": getattr(snapshot, "prev_atr_14", None),
            "price_change_7d": price_change_7d,
        }
        regime, confidence = detect_market_regime(indicators, volatility)
        regimes[timeframe] = RegimeRead(timeframe=timeframe, regime=regime, confidence=confidence)
    return regimes


def primary_regime(regimes: dict[int, RegimeRead]) -> str | None:
    for timeframe in (1440, 240, 60, 15):
        if timeframe in regimes:
            return regimes[timeframe].regime
    return None


def serialize_regime_map(regimes: dict[int, RegimeRead]) -> dict[str, dict[str, float | str]]:
    return {
        str(timeframe): {
            "regime": item.regime,
            "confidence": item.confidence,
        }
        for timeframe, item in sorted(regimes.items())
    }


def read_regime_details(regime_details: dict[str, Any] | None, timeframe: int) -> RegimeRead | None:
    if not regime_details:
        return None
    payload = regime_details.get(str(timeframe))
    if not isinstance(payload, dict):
        return None
    regime = payload.get("regime")
    confidence = payload.get("confidence")
    if not isinstance(regime, str):
        return None
    try:
        normalized_confidence = float(confidence)
    except (TypeError, ValueError):
        normalized_confidence = 0.0
    return RegimeRead(
        timeframe=timeframe,
        regime=regime,
        confidence=normalized_confidence,
    )


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
