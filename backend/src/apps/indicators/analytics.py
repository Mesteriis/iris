import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from src.apps.indicators.domain import (
    adx_series,
    atr_series,
    bollinger_bands,
    ema_series,
    macd_series,
    rsi_series,
    sma_series,
)
from src.apps.market_data.domain import ensure_utc
from src.apps.market_data.models import Coin
from src.apps.market_data.candles import (
    BASE_TIMEFRAME_MINUTES,
    CandlePoint,
    candle_close_timestamp,
    interval_to_timeframe,
    timeframe_delta,
)
from src.apps.market_data.sources.base import RateLimitedMarketSourceError
from src.apps.market_data.sources.rate_limits import rate_limited_get
from src.apps.patterns.domain.scheduler import (
    analysis_priority_for_bucket,
    assign_activity_bucket,
    calculate_activity_score,
)

LOGGER = logging.getLogger(__name__)

INDICATOR_VERSION = 1
PRICE_HISTORY_LOOKBACK_BARS = 220
COINGECKO_MARKET_URL = "https://api.coingecko.com/api/v3/coins/markets"
COINGECKO_MARKET_CAP_IDS: dict[str, str] = {
    "AKTUSD": "akash-network",
    "BTCUSD": "bitcoin",
    "DOGEUSD": "dogecoin",
    "ETHUSD": "ethereum",
    "RENDERUSD": "render-token",
    "SOLUSD": "solana",
    "TAOUSD": "bittensor",
}
SIGNAL_TYPES = {
    "golden_cross",
    "death_cross",
    "bullish_breakout",
    "bearish_breakdown",
    "trend_reversal",
    "volume_spike",
    "rsi_oversold",
    "rsi_overbought",
}


@dataclass(slots=True, frozen=True)
class CandleAnalyticsEvent:
    coin_id: int
    timeframe: int
    timestamp: datetime


@dataclass(slots=True, frozen=True)
class TimeframeSnapshot:
    timeframe: int
    feature_source: str
    candle_timestamp: datetime
    candle_close_timestamp: datetime
    price_current: float
    ema_20: float | None
    ema_50: float | None
    ema_200: float | None
    sma_50: float | None
    sma_200: float | None
    rsi_14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    atr_14: float | None
    prev_atr_14: float | None
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None
    bb_width: float | None
    prev_bb_width: float | None
    adx_14: float | None
    current_volume: float | None
    average_volume_20: float | None
    range_high_20: float | None
    range_low_20: float | None
    prev_price_current: float | None
    prev_sma_50: float | None
    prev_sma_200: float | None
    prev_rsi_14: float | None
    prev_macd_histogram: float | None
    prev_ema_20: float | None
    prev_ema_50: float | None


def _coin_base_timeframe(coin: Coin) -> int:
    candles = coin.candles_config or []
    if not candles:
        return BASE_TIMEFRAME_MINUTES
    return min(
        interval_to_timeframe(str(candle["interval"]))
        for candle in candles
        if "interval" in candle
    )


def determine_affected_timeframes(*, timeframe: int, timestamp: datetime) -> list[int]:
    affected = [timeframe]
    close_time = candle_close_timestamp(timestamp, timeframe)
    if timeframe < 60 and close_time.minute == 0:
        affected.append(60)
    if timeframe < 240 and close_time.minute == 0 and close_time.hour % 4 == 0:
        affected.append(240)
    if timeframe < 1440 and close_time.minute == 0 and close_time.hour == 0:
        affected.append(1440)
    return affected


def _series_value_pair(values: Sequence[float | None]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    return values[-1], values[-2] if len(values) > 1 else None


def _calculate_snapshot(
    candles: Sequence[CandlePoint],
    timeframe: int,
    *,
    feature_source: str,
) -> TimeframeSnapshot | None:
    if not candles:
        return None

    closes = [float(item.close) for item in candles]
    highs = [float(item.high) for item in candles]
    lows = [float(item.low) for item in candles]
    volumes = [float(item.volume or 0.0) for item in candles]

    ema_20_series = ema_series(closes, 20)
    ema_50_series = ema_series(closes, 50)
    ema_200_series = ema_series(closes, 200)
    sma_50_series = sma_series(closes, 50)
    sma_200_series = sma_series(closes, 200)
    rsi_14_series = rsi_series(closes, 14)
    macd_line, macd_signal_line, macd_histogram = macd_series(closes)
    atr_14_series = atr_series(highs, lows, closes, 14)
    bb_upper_series, bb_middle_series, bb_lower_series, bb_width_series = bollinger_bands(closes, period=20)
    adx_14_series = adx_series(highs, lows, closes, 14)

    price_current = closes[-1]
    ema_20, prev_ema_20 = _series_value_pair(ema_20_series)
    ema_50, prev_ema_50 = _series_value_pair(ema_50_series)
    ema_200, _ = _series_value_pair(ema_200_series)
    sma_50, prev_sma_50 = _series_value_pair(sma_50_series)
    sma_200, prev_sma_200 = _series_value_pair(sma_200_series)
    rsi_14, prev_rsi_14 = _series_value_pair(rsi_14_series)
    macd, _ = _series_value_pair(macd_line)
    macd_signal, _ = _series_value_pair(macd_signal_line)
    macd_histogram_value, prev_macd_histogram = _series_value_pair(macd_histogram)
    atr_14, _ = _series_value_pair(atr_14_series)
    prev_atr_14 = atr_14_series[-2] if len(atr_14_series) > 1 else None
    bb_upper, _ = _series_value_pair(bb_upper_series)
    bb_middle, _ = _series_value_pair(bb_middle_series)
    bb_lower, _ = _series_value_pair(bb_lower_series)
    bb_width, _ = _series_value_pair(bb_width_series)
    prev_bb_width = bb_width_series[-2] if len(bb_width_series) > 1 else None
    adx_14, _ = _series_value_pair(adx_14_series)

    average_volume_20 = sum(volumes[-20:]) / min(len(volumes), 20) if volumes else None
    range_source = candles[-21:-1] if len(candles) > 20 else candles[:-1]
    range_high_20 = max((item.high for item in range_source), default=None)
    range_low_20 = min((item.low for item in range_source), default=None)
    prev_price_current = closes[-2] if len(closes) > 1 else None

    return TimeframeSnapshot(
        timeframe=timeframe,
        feature_source=feature_source,
        candle_timestamp=ensure_utc(candles[-1].timestamp),
        candle_close_timestamp=candle_close_timestamp(candles[-1].timestamp, timeframe),
        price_current=price_current,
        ema_20=ema_20,
        ema_50=ema_50,
        ema_200=ema_200,
        sma_50=sma_50,
        sma_200=sma_200,
        rsi_14=rsi_14,
        macd=macd,
        macd_signal=macd_signal,
        macd_histogram=macd_histogram_value,
        atr_14=atr_14,
        prev_atr_14=prev_atr_14,
        bb_upper=bb_upper,
        bb_middle=bb_middle,
        bb_lower=bb_lower,
        bb_width=bb_width,
        prev_bb_width=prev_bb_width,
        adx_14=adx_14,
        current_volume=volumes[-1] if volumes else None,
        average_volume_20=average_volume_20,
        range_high_20=float(range_high_20) if range_high_20 is not None else None,
        range_low_20=float(range_low_20) if range_low_20 is not None else None,
        prev_price_current=prev_price_current,
        prev_sma_50=prev_sma_50,
        prev_sma_200=prev_sma_200,
        prev_rsi_14=prev_rsi_14,
        prev_macd_histogram=prev_macd_histogram,
        prev_ema_20=prev_ema_20,
        prev_ema_50=prev_ema_50,
    )


def _compute_price_change(base_candles: Sequence[CandlePoint], delta: timedelta) -> float | None:
    if not base_candles:
        return None
    latest = base_candles[-1]
    target_timestamp = ensure_utc(latest.timestamp) - delta
    candidate: CandlePoint | None = None
    for candle in reversed(base_candles):
        if ensure_utc(candle.timestamp) <= target_timestamp:
            candidate = candle
            break
    if candidate is None:
        return None
    return float(latest.close) - float(candidate.close)


def _compute_volume_metrics(
    base_candles: Sequence[CandlePoint],
    base_timeframe: int,
) -> tuple[float | None, float | None, float | None]:
    if not base_candles:
        return None, None, None
    bars_per_day = max(int(timedelta(hours=24) / timeframe_delta(base_timeframe)), 1)
    current_window = base_candles[-bars_per_day:]
    previous_window = base_candles[-bars_per_day * 2 : -bars_per_day]
    volume_24h = sum(float(item.volume or 0.0) for item in current_window) if current_window else None
    previous_volume_24h = sum(float(item.volume or 0.0) for item in previous_window) if previous_window else None
    if previous_volume_24h is None or previous_volume_24h == 0 or volume_24h is None:
        volume_change_24h = None
    else:
        volume_change_24h = ((volume_24h - previous_volume_24h) / previous_volume_24h) * 100
    closes = [float(item.close) for item in current_window]
    if len(closes) < 2:
        volatility = None
    else:
        mean = sum(closes) / len(closes)
        variance = sum((value - mean) ** 2 for value in closes) / len(closes)
        volatility = variance**0.5
    return volume_24h, volume_change_24h, volatility


def _snapshot_completeness(snapshot: TimeframeSnapshot) -> int:
    return sum(
        value is not None
        for value in (
            snapshot.ema_20,
            snapshot.ema_50,
            snapshot.sma_50,
            snapshot.sma_200,
            snapshot.rsi_14,
            snapshot.macd,
            snapshot.macd_signal,
            snapshot.macd_histogram,
            snapshot.atr_14,
            snapshot.bb_width,
            snapshot.adx_14,
        )
    )


def _select_primary_snapshot(snapshots: dict[int, TimeframeSnapshot]) -> TimeframeSnapshot | None:
    if not snapshots:
        return None
    return max(
        snapshots.values(),
        key=lambda snapshot: (_snapshot_completeness(snapshot), snapshot.timeframe),
    )


def _compute_trend(primary: TimeframeSnapshot) -> str:
    if primary.sma_200 is None or primary.ema_50 is None or primary.macd_histogram is None:
        return "sideways"
    if primary.price_current > primary.sma_200 and primary.ema_50 > primary.sma_200 and primary.macd_histogram > 0:
        return "bullish"
    if primary.price_current < primary.sma_200:
        return "bearish"
    return "sideways"


def _compute_trend_score(primary: TimeframeSnapshot, volume_change_24h: float | None) -> int:
    score = 50.0
    if primary.ema_20 is not None and primary.ema_50 is not None:
        score += 15 if primary.ema_20 > primary.ema_50 else -15
    if primary.price_current is not None and primary.sma_200 is not None:
        score += 20 if primary.price_current > primary.sma_200 else -20
    if primary.macd_histogram is not None:
        score += 15 if primary.macd_histogram > 0 else -15
    if primary.rsi_14 is not None:
        if 55 <= primary.rsi_14 <= 70:
            score += 10
        elif primary.rsi_14 < 40:
            score -= 10
    if primary.adx_14 is not None:
        if primary.adx_14 >= 25:
            score += 10
        elif primary.adx_14 < 15:
            score -= 5
    if volume_change_24h is not None:
        if volume_change_24h > 10:
            score += 10
        elif volume_change_24h < -10:
            score -= 10
    return max(0, min(100, int(round(score))))


def _activity_fields(
    *,
    price_change_24h: float | None,
    volatility: float | None,
    volume_change_24h: float | None,
    price_current: float | None,
) -> tuple[float, str, int]:
    activity_score = calculate_activity_score(
        price_change_24h=price_change_24h,
        volatility=volatility,
        volume_change_24h=volume_change_24h,
        price_current=price_current,
    )
    activity_bucket = assign_activity_bucket(activity_score)
    analysis_priority = analysis_priority_for_bucket(activity_bucket)
    return activity_score, activity_bucket, analysis_priority


def _compute_market_regime(primary: TimeframeSnapshot, trend: str, volume_change_24h: float | None) -> str | None:
    if primary.sma_200 is None or primary.macd is None:
        return None
    if primary.price_current > primary.sma_200 and primary.macd > 0:
        return "bull_market"
    if primary.price_current < primary.sma_200 and primary.macd < 0:
        return "bear_market"
    if trend == "sideways" and (primary.bb_width or 0) < 0.08 and (volume_change_24h or 0) >= 0:
        return "accumulation"
    if trend == "sideways" and (volume_change_24h or 0) < 0:
        return "distribution"
    return "accumulation" if trend == "bullish" else "distribution"


async def _fetch_market_cap(symbol: str) -> float | None:
    gecko_id = COINGECKO_MARKET_CAP_IDS.get(symbol)
    if gecko_id is None:
        return None
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=15.0),
            headers={"User-Agent": "IRIS/0.1 analytics", "Accept": "application/json"},
        ) as client:
            response = await rate_limited_get(
                "coingecko",
                client,
                COINGECKO_MARKET_URL,
                params={
                    "vs_currency": "usd",
                    "ids": gecko_id,
                    "order": "market_cap_desc",
                    "per_page": 1,
                    "page": 1,
                    "sparkline": "false",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except RateLimitedMarketSourceError as exc:  # pragma: no cover
        LOGGER.warning("Market cap lookup rate limited for %s: retry_after=%s", symbol, exc.retry_after_seconds)
        return None
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Market cap lookup failed for %s: %s", symbol, exc)
        return None
    if not payload:
        return None
    value = payload[0].get("market_cap")
    return float(value) if value is not None else None


def _detect_signals(snapshot: TimeframeSnapshot) -> list[dict[str, object]]:
    detected: list[dict[str, object]] = []
    candle_time = snapshot.candle_close_timestamp

    if (
        snapshot.prev_sma_50 is not None
        and snapshot.prev_sma_200 is not None
        and snapshot.sma_50 is not None
        and snapshot.sma_200 is not None
    ):
        if snapshot.prev_sma_50 <= snapshot.prev_sma_200 and snapshot.sma_50 > snapshot.sma_200:
            detected.append({"signal_type": "golden_cross", "confidence": 0.92, "candle_timestamp": candle_time})
        if snapshot.prev_sma_50 >= snapshot.prev_sma_200 and snapshot.sma_50 < snapshot.sma_200:
            detected.append({"signal_type": "death_cross", "confidence": 0.92, "candle_timestamp": candle_time})

    if snapshot.range_high_20 is not None and snapshot.price_current > snapshot.range_high_20 and (snapshot.current_volume or 0) > (snapshot.average_volume_20 or 0) * 1.5:
        detected.append({"signal_type": "bullish_breakout", "confidence": 0.85, "candle_timestamp": candle_time})
    if snapshot.range_low_20 is not None and snapshot.price_current < snapshot.range_low_20 and (snapshot.current_volume or 0) > (snapshot.average_volume_20 or 0) * 1.5:
        detected.append({"signal_type": "bearish_breakdown", "confidence": 0.85, "candle_timestamp": candle_time})

    if snapshot.prev_macd_histogram is not None and snapshot.macd_histogram is not None:
        if snapshot.prev_macd_histogram <= 0 < snapshot.macd_histogram:
            detected.append({"signal_type": "trend_reversal", "confidence": 0.74, "candle_timestamp": candle_time})
        if snapshot.prev_macd_histogram >= 0 > snapshot.macd_histogram:
            detected.append({"signal_type": "trend_reversal", "confidence": 0.74, "candle_timestamp": candle_time})

    if snapshot.current_volume is not None and snapshot.average_volume_20 is not None and snapshot.current_volume > snapshot.average_volume_20 * 2:
        detected.append({"signal_type": "volume_spike", "confidence": 0.7, "candle_timestamp": candle_time})

    if snapshot.prev_rsi_14 is not None and snapshot.rsi_14 is not None:
        if snapshot.prev_rsi_14 >= 30 > snapshot.rsi_14:
            detected.append({"signal_type": "rsi_oversold", "confidence": 0.68, "candle_timestamp": candle_time})
        if snapshot.prev_rsi_14 <= 70 < snapshot.rsi_14:
            detected.append({"signal_type": "rsi_overbought", "confidence": 0.68, "candle_timestamp": candle_time})

    return detected


__all__ = [
    "BASE_TIMEFRAME_MINUTES",
    "COINGECKO_MARKET_CAP_IDS",
    "COINGECKO_MARKET_URL",
    "CandleAnalyticsEvent",
    "INDICATOR_VERSION",
    "PRICE_HISTORY_LOOKBACK_BARS",
    "SIGNAL_TYPES",
    "TimeframeSnapshot",
    "_activity_fields",
    "_calculate_snapshot",
    "_coin_base_timeframe",
    "_compute_market_regime",
    "_compute_price_change",
    "_compute_trend",
    "_compute_trend_score",
    "_compute_volume_metrics",
    "_detect_signals",
    "_fetch_market_cap",
    "_select_primary_snapshot",
    "_series_value_pair",
    "_snapshot_completeness",
    "adx_series",
    "atr_series",
    "bollinger_bands",
    "determine_affected_timeframes",
    "ema_series",
    "macd_series",
    "rsi_series",
    "sma_series",
]
