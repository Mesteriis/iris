from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.indicators.models import CoinMetrics
from app.apps.market_data.repos import timeframe_delta
from app.apps.market_data.domain import ensure_utc

ACTIVITY_BUCKETS = ("HOT", "WARM", "COLD", "DEAD")
ANALYSIS_PRIORITY_BY_BUCKET = {
    "HOT": 100,
    "WARM": 70,
    "COLD": 30,
    "DEAD": 5,
}


def calculate_activity_score(
    *,
    price_change_24h: float | None,
    volatility: float | None,
    volume_change_24h: float | None,
    price_current: float | None,
) -> float:
    base_price = abs(float(price_current or 0.0))
    normalized_price_change = (
        (abs(float(price_change_24h or 0.0)) / base_price) * 100
        if base_price > 0
        else abs(float(price_change_24h or 0.0))
    )
    normalized_volatility = (
        (abs(float(volatility or 0.0)) / base_price) * 100
        if base_price > 0
        else abs(float(volatility or 0.0))
    )
    normalized_volume_change = abs(float(volume_change_24h or 0.0))
    return round(normalized_price_change + normalized_volatility + normalized_volume_change, 4)


def assign_activity_bucket(activity_score: float | None) -> str:
    score = float(activity_score or 0.0)
    if score > 70:
        return "HOT"
    if score >= 40:
        return "WARM"
    if score >= 15:
        return "COLD"
    return "DEAD"


def analysis_priority_for_bucket(bucket: str | None) -> int:
    return ANALYSIS_PRIORITY_BY_BUCKET.get((bucket or "DEAD").upper(), ANALYSIS_PRIORITY_BY_BUCKET["DEAD"])


def analysis_interval(bucket: str | None, timeframe: int) -> timedelta:
    normalized_bucket = (bucket or "DEAD").upper()
    if normalized_bucket == "HOT":
        return timeframe_delta(timeframe)
    if normalized_bucket == "WARM":
        return timeframe_delta(timeframe) * 2
    if normalized_bucket == "COLD":
        return timeframe_delta(timeframe) * 10
    return max(timeframe_delta(timeframe), timedelta(hours=1))


def should_request_analysis(
    *,
    timeframe: int,
    timestamp: datetime,
    activity_bucket: str | None,
    last_analysis_at: datetime | None,
) -> bool:
    event_timestamp = ensure_utc(timestamp)
    if last_analysis_at is None:
        return True
    previous_timestamp = ensure_utc(last_analysis_at)
    return event_timestamp >= previous_timestamp + analysis_interval(activity_bucket, timeframe)


def mark_analysis_requested(
    db: Session,
    *,
    coin_id: int,
    analysis_timestamp: datetime,
) -> None:
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
    if metrics is None:
        return
    metrics.last_analysis_at = ensure_utc(analysis_timestamp)
    db.commit()


def get_activity_snapshot(db: Session, *, coin_id: int) -> CoinMetrics | None:
    return db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
