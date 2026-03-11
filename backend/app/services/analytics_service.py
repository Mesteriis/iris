from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Sequence

import httpx
from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.candle import Candle
from app.models.coin import Coin
from app.models.coin_metrics import CoinMetrics
from app.models.indicator_cache import IndicatorCache
from app.models.signal import Signal
from app.services.analytics_events import NewCandleEvent, clear_new_candle_event_if_unchanged, list_new_candle_events
from app.services.candles_service import (
    AGGREGATE_VIEW_BY_TIMEFRAME,
    BASE_TIMEFRAME_MINUTES,
    CandlePoint,
    TIMEFRAME_INTERVALS,
    aggregate_has_rows,
    candle_close_timestamp,
    fetch_candle_points,
    get_base_candle_bounds,
    interval_to_timeframe,
    refresh_continuous_aggregate_range,
    refresh_continuous_aggregate_window,
    timeframe_delta,
)
from app.services.indicator_engine import adx_series, atr_series, bollinger_bands, ema_series, macd_series, rsi_series, sma_series
from app.services.market_data import ensure_utc, utc_now
from app.services.market_sources.base import RateLimitedMarketSourceError
from app.services.market_sources.rate_limits import rate_limited_get

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
class TimeframeSnapshot:
    timeframe: int
    feature_source: str
    candle_timestamp: datetime
    candle_close_timestamp: datetime
    price_current: float
    ema_20: float | None
    ema_50: float | None
    sma_50: float | None
    sma_200: float | None
    rsi_14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    atr_14: float | None
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None
    bb_width: float | None
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


def _has_direct_candles(db: Session, coin_id: int, timeframe: int) -> bool:
    return db.scalar(
        select(Candle.coin_id)
        .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
        .limit(1)
    ) is not None


def ensure_coin_metrics_row(db: Session, coin_id: int) -> None:
    stmt = insert(CoinMetrics).values({"coin_id": coin_id, "updated_at": utc_now(), "indicator_version": INDICATOR_VERSION})
    stmt = stmt.on_conflict_do_nothing(index_elements=["coin_id"])
    db.execute(stmt)


def delete_coin_metrics_row(db: Session, coin_id: int) -> None:
    db.execute(delete(CoinMetrics).where(CoinMetrics.coin_id == coin_id))


def list_coin_metrics(db: Session) -> Sequence[dict[str, Any]]:
    rows = db.execute(
        select(
            Coin.id.label("coin_id"),
            Coin.symbol,
            Coin.name,
            CoinMetrics.price_current,
            CoinMetrics.price_change_1h,
            CoinMetrics.price_change_24h,
            CoinMetrics.price_change_7d,
            CoinMetrics.ema_20,
            CoinMetrics.ema_50,
            CoinMetrics.sma_50,
            CoinMetrics.sma_200,
            CoinMetrics.rsi_14,
            CoinMetrics.macd,
            CoinMetrics.macd_signal,
            CoinMetrics.macd_histogram,
            CoinMetrics.atr_14,
            CoinMetrics.bb_upper,
            CoinMetrics.bb_middle,
            CoinMetrics.bb_lower,
            CoinMetrics.bb_width,
            CoinMetrics.adx_14,
            CoinMetrics.volume_24h,
            CoinMetrics.volume_change_24h,
            CoinMetrics.volatility,
            CoinMetrics.market_cap,
            CoinMetrics.trend,
            CoinMetrics.trend_score,
            CoinMetrics.market_regime,
            CoinMetrics.indicator_version,
            CoinMetrics.updated_at,
        )
        .join(CoinMetrics, CoinMetrics.coin_id == Coin.id)
        .where(Coin.deleted_at.is_(None))
        .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
    ).all()
    return [dict(row._mapping) for row in rows]


def list_signals(
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
) -> Sequence[dict[str, Any]]:
    stmt = (
        select(
            Signal.coin_id,
            Coin.symbol,
            Coin.name,
            Signal.timeframe,
            Signal.signal_type,
            Signal.confidence,
            Signal.candle_timestamp,
            Signal.created_at,
        )
        .join(Coin, Coin.id == Signal.coin_id)
        .where(Coin.deleted_at.is_(None))
        .order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc())
        .limit(max(limit, 1))
    )
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    if timeframe is not None:
        stmt = stmt.where(Signal.timeframe == timeframe)
    rows = db.execute(stmt).all()
    return [dict(row._mapping) for row in rows]


def list_repair_new_candle_events(db: Session) -> list[NewCandleEvent]:
    latest_indicator_per_coin = (
        select(
            IndicatorCache.coin_id,
            IndicatorCache.timeframe,
            func.max(IndicatorCache.timestamp).label("last_indicator_timestamp"),
        )
        .where(
            IndicatorCache.indicator == "price_current",
            IndicatorCache.indicator_version == INDICATOR_VERSION,
        )
        .group_by(IndicatorCache.coin_id, IndicatorCache.timeframe)
        .subquery()
    )
    repair_rows = db.execute(
        select(
            Candle.coin_id.label("coin_id"),
            Candle.timeframe.label("timeframe"),
            func.max(Candle.timestamp).label("latest_timestamp"),
            latest_indicator_per_coin.c.last_indicator_timestamp,
        )
        .join(Coin, Coin.id == Candle.coin_id)
        .outerjoin(
            latest_indicator_per_coin,
            and_(
                latest_indicator_per_coin.c.coin_id == Candle.coin_id,
                latest_indicator_per_coin.c.timeframe == Candle.timeframe,
            ),
        )
        .where(Coin.deleted_at.is_(None))
        .group_by(Candle.coin_id, Candle.timeframe, latest_indicator_per_coin.c.last_indicator_timestamp)
    ).all()
    events: list[NewCandleEvent] = []
    for row in repair_rows:
        if row.latest_timestamp is None:
            continue
        latest_timestamp = ensure_utc(row.latest_timestamp)
        last_indicator_timestamp = ensure_utc(row.last_indicator_timestamp) if row.last_indicator_timestamp is not None else None
        if last_indicator_timestamp is None or latest_timestamp > last_indicator_timestamp:
            events.append(NewCandleEvent(coin_id=int(row.coin_id), timeframe=int(row.timeframe), timestamp=latest_timestamp))
    return events


def list_pending_new_candle_events(db: Session) -> list[NewCandleEvent]:
    events: dict[tuple[int, int], NewCandleEvent] = {}
    for event in list_new_candle_events():
        events[(event.coin_id, event.timeframe)] = event
    for event in list_repair_new_candle_events(db):
        key = (event.coin_id, event.timeframe)
        existing = events.get(key)
        if existing is None or event.timestamp > existing.timestamp:
            events[key] = event
    return sorted(events.values(), key=lambda item: (item.timestamp, item.coin_id, item.timeframe))


def determine_affected_timeframes(event: NewCandleEvent) -> list[int]:
    affected = [event.timeframe]
    close_time = candle_close_timestamp(event.timestamp, event.timeframe)
    if event.timeframe < 60 and close_time.minute == 0:
        affected.append(60)
    if event.timeframe < 240 and close_time.minute == 0 and close_time.hour % 4 == 0:
        affected.append(240)
    if event.timeframe < 1440 and close_time.minute == 0 and close_time.hour == 0:
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
    sma_50, prev_sma_50 = _series_value_pair(sma_50_series)
    sma_200, prev_sma_200 = _series_value_pair(sma_200_series)
    rsi_14, prev_rsi_14 = _series_value_pair(rsi_14_series)
    macd, _ = _series_value_pair(macd_line)
    macd_signal, _ = _series_value_pair(macd_signal_line)
    macd_histogram_value, prev_macd_histogram = _series_value_pair(macd_histogram)
    atr_14, _ = _series_value_pair(atr_14_series)
    bb_upper, _ = _series_value_pair(bb_upper_series)
    bb_middle, _ = _series_value_pair(bb_middle_series)
    bb_lower, _ = _series_value_pair(bb_lower_series)
    bb_width, _ = _series_value_pair(bb_width_series)
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
        sma_50=sma_50,
        sma_200=sma_200,
        rsi_14=rsi_14,
        macd=macd,
        macd_signal=macd_signal,
        macd_histogram=macd_histogram_value,
        atr_14=atr_14,
        bb_upper=bb_upper,
        bb_middle=bb_middle,
        bb_lower=bb_lower,
        bb_width=bb_width,
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


def _fetch_market_cap(symbol: str) -> float | None:
    gecko_id = COINGECKO_MARKET_CAP_IDS.get(symbol)
    if gecko_id is None:
        return None
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=15.0),
            headers={"User-Agent": "IRIS/0.1 analytics", "Accept": "application/json"},
        ) as client:
            response = rate_limited_get(
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


def _store_indicator_cache(db: Session, coin_id: int, snapshots: Sequence[TimeframeSnapshot], volume_24h: float | None, volume_change_24h: float | None) -> None:
    rows: list[dict[str, Any]] = []
    for snapshot in snapshots:
        values = {
            "price_current": snapshot.price_current,
            "ema_20": snapshot.ema_20,
            "ema_50": snapshot.ema_50,
            "sma_50": snapshot.sma_50,
            "sma_200": snapshot.sma_200,
            "rsi_14": snapshot.rsi_14,
            "macd": snapshot.macd,
            "macd_signal": snapshot.macd_signal,
            "macd_histogram": snapshot.macd_histogram,
            "atr_14": snapshot.atr_14,
            "bb_upper": snapshot.bb_upper,
            "bb_middle": snapshot.bb_middle,
            "bb_lower": snapshot.bb_lower,
            "bb_width": snapshot.bb_width,
            "adx_14": snapshot.adx_14,
        }
        if snapshot.timeframe == BASE_TIMEFRAME_MINUTES:
            values["volume_24h"] = volume_24h
            values["volume_change_24h"] = volume_change_24h
        for indicator_name, indicator_value in values.items():
            rows.append(
                {
                    "coin_id": coin_id,
                    "timeframe": snapshot.timeframe,
                    "indicator": indicator_name,
                    "value": indicator_value,
                    "timestamp": snapshot.candle_timestamp,
                    "indicator_version": INDICATOR_VERSION,
                    "feature_source": snapshot.feature_source,
                }
            )
    if not rows:
        return
    stmt = insert(IndicatorCache).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["coin_id", "timeframe", "indicator", "timestamp", "indicator_version"],
        set_={
            "value": stmt.excluded.value,
            "feature_source": stmt.excluded.feature_source,
        },
    )
    db.execute(stmt)
    db.commit()


def _insert_signals(db: Session, coin_id: int, timeframe: int, signals: Sequence[dict[str, Any]]) -> None:
    if not signals:
        return
    rows = [
        {
            "coin_id": coin_id,
            "timeframe": timeframe,
            "signal_type": item["signal_type"],
            "confidence": item["confidence"],
            "candle_timestamp": item["candle_timestamp"],
        }
        for item in signals
        if item["signal_type"] in SIGNAL_TYPES
    ]
    if not rows:
        return
    stmt = insert(Signal).values(rows)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["coin_id", "timeframe", "candle_timestamp", "signal_type"],
    )
    db.execute(stmt)
    db.commit()


def _detect_signals(snapshot: TimeframeSnapshot) -> list[dict[str, Any]]:
    detected: list[dict[str, Any]] = []
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


def _upsert_coin_metrics(
    db: Session,
    coin: Coin,
    *,
    base_timeframe: int,
    primary: TimeframeSnapshot | None,
    base_snapshot: TimeframeSnapshot | None,
    volume_24h: float | None,
    volume_change_24h: float | None,
    volatility: float | None,
    refresh_market_cap: bool,
) -> None:
    ensure_coin_metrics_row(db, coin.id)

    if primary is None:
        return

    trend = _compute_trend(primary)
    trend_score = _compute_trend_score(primary, volume_change_24h)
    market_regime = _compute_market_regime(primary, trend, volume_change_24h)
    base_candles = fetch_candle_points(db, coin.id, base_timeframe, 800)
    existing_market_cap = db.scalar(select(CoinMetrics.market_cap).where(CoinMetrics.coin_id == coin.id))
    payload = {
        "coin_id": coin.id,
        "price_current": base_snapshot.price_current if base_snapshot is not None else primary.price_current,
        "price_change_1h": _compute_price_change(base_candles, timedelta(hours=1)),
        "price_change_24h": _compute_price_change(base_candles, timedelta(hours=24)),
        "price_change_7d": _compute_price_change(base_candles, timedelta(days=7)),
        "ema_20": primary.ema_20,
        "ema_50": primary.ema_50,
        "sma_50": primary.sma_50,
        "sma_200": primary.sma_200,
        "rsi_14": primary.rsi_14,
        "macd": primary.macd,
        "macd_signal": primary.macd_signal,
        "macd_histogram": primary.macd_histogram,
        "atr_14": primary.atr_14,
        "bb_upper": primary.bb_upper,
        "bb_middle": primary.bb_middle,
        "bb_lower": primary.bb_lower,
        "bb_width": primary.bb_width,
        "adx_14": primary.adx_14,
        "volume_24h": volume_24h,
        "volume_change_24h": volume_change_24h,
        "volatility": volatility,
        "market_cap": _fetch_market_cap(coin.symbol) if refresh_market_cap or existing_market_cap is None else existing_market_cap,
        "trend": trend,
        "trend_score": trend_score,
        "market_regime": market_regime,
        "indicator_version": INDICATOR_VERSION,
        "updated_at": utc_now(),
    }
    stmt = insert(CoinMetrics).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["coin_id"],
        set_={column: getattr(stmt.excluded, column) for column in payload.keys() if column != "coin_id"},
    )
    db.execute(stmt)
    db.commit()


def handle_new_candle_event(db: Session, event: NewCandleEvent) -> dict[str, Any]:
    coin = db.get(Coin, event.coin_id)
    if coin is None or coin.deleted_at is not None:
        clear_new_candle_event_if_unchanged(event)
        return {"status": "skipped", "reason": "coin_not_found", "coin_id": event.coin_id}

    base_timeframe = _coin_base_timeframe(coin)

    base_window_start, base_window_end = get_base_candle_bounds(db, coin.id)
    if base_window_start is not None and base_window_end is not None:
        for timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
            if not aggregate_has_rows(db, coin.id, timeframe):
                refresh_continuous_aggregate_range(db, timeframe, base_window_start, base_window_end)

    affected_timeframes = determine_affected_timeframes(event)
    for timeframe in affected_timeframes:
        if timeframe in AGGREGATE_VIEW_BY_TIMEFRAME:
            refresh_continuous_aggregate_window(db, timeframe, event.timestamp)

    snapshots: dict[int, TimeframeSnapshot] = {}
    for timeframe in TIMEFRAME_INTERVALS:
        candles = fetch_candle_points(db, coin.id, timeframe, PRICE_HISTORY_LOOKBACK_BARS)
        feature_source = (
            "candles"
            if _has_direct_candles(db, coin.id, timeframe) or base_timeframe != BASE_TIMEFRAME_MINUTES
            else AGGREGATE_VIEW_BY_TIMEFRAME.get(timeframe, "candles")
        )
        snapshot = _calculate_snapshot(candles, timeframe, feature_source=feature_source)
        if snapshot is not None:
            snapshots[timeframe] = snapshot

    base_candles = fetch_candle_points(db, coin.id, base_timeframe, 400)
    volume_24h, volume_change_24h, volatility = _compute_volume_metrics(base_candles, base_timeframe)

    snapshot_priority = [1440, 240, 60, 15]
    primary = next((snapshots[timeframe] for timeframe in snapshot_priority if timeframe in snapshots), None)
    base_snapshot = snapshots.get(base_timeframe)
    _upsert_coin_metrics(
        db,
        coin,
        base_timeframe=base_timeframe,
        primary=primary,
        base_snapshot=base_snapshot,
        volume_24h=volume_24h,
        volume_change_24h=volume_change_24h,
        volatility=volatility,
        refresh_market_cap=240 in affected_timeframes or 1440 in affected_timeframes,
    )
    _store_indicator_cache(
        db,
        coin.id,
        [snapshots[timeframe] for timeframe in affected_timeframes if timeframe in snapshots],
        volume_24h,
        volume_change_24h,
    )
    for timeframe in affected_timeframes:
        snapshot = snapshots.get(timeframe)
        if snapshot is None:
            continue
        _insert_signals(db, coin.id, timeframe, _detect_signals(snapshot))

    clear_new_candle_event_if_unchanged(event)
    return {
        "status": "ok",
        "coin_id": coin.id,
        "symbol": coin.symbol,
        "timeframes": affected_timeframes,
        "indicator_version": INDICATOR_VERSION,
    }
