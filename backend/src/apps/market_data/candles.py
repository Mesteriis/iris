from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.apps.market_data.domain import ensure_utc, normalize_interval

BASE_TIMEFRAME_MINUTES = 15
TIMEFRAME_INTERVALS: dict[int, str] = {
    15: "15m",
    60: "1h",
    240: "4h",
    1440: "1d",
}
INTERVAL_TO_TIMEFRAME: dict[str, int] = {value: key for key, value in TIMEFRAME_INTERVALS.items()}
AGGREGATE_VIEW_BY_TIMEFRAME: dict[int, str] = {
    60: "candles_1h",
    240: "candles_4h",
    1440: "candles_1d",
}


@dataclass(slots=True, frozen=True)
class CandlePoint:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None


def timeframe_bucket_interval(timeframe: int) -> str:
    if timeframe == 1440:
        return "1 day"
    hours = timeframe // 60
    return f"{hours} hour" if hours == 1 else f"{hours} hours"


def timeframe_delta(timeframe: int) -> timedelta:
    return timedelta(minutes=int(timeframe))


def interval_to_timeframe(interval: str) -> int:
    return INTERVAL_TO_TIMEFRAME[normalize_interval(interval)]


def align_timeframe_timestamp(value: datetime, timeframe: int) -> datetime:
    current = ensure_utc(value)
    seconds = int(timeframe_delta(timeframe).total_seconds())
    aligned = int(current.timestamp()) // seconds * seconds
    return datetime.fromtimestamp(aligned, tz=timezone.utc)


def candle_close_timestamp(value: datetime, timeframe: int) -> datetime:
    return ensure_utc(value) + timeframe_delta(timeframe)


__all__ = [
    "AGGREGATE_VIEW_BY_TIMEFRAME",
    "BASE_TIMEFRAME_MINUTES",
    "CandlePoint",
    "INTERVAL_TO_TIMEFRAME",
    "TIMEFRAME_INTERVALS",
    "align_timeframe_timestamp",
    "candle_close_timestamp",
    "interval_to_timeframe",
    "timeframe_bucket_interval",
    "timeframe_delta",
]
