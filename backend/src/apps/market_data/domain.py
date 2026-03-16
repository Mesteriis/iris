from datetime import UTC, datetime, timedelta

INTERVAL_TO_DELTA: dict[str, timedelta] = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_interval(interval: str) -> str:
    normalized = interval.strip().lower()
    if normalized not in INTERVAL_TO_DELTA:
        raise ValueError(f"Unsupported interval '{interval}'.")
    return normalized


def interval_delta(interval: str) -> timedelta:
    return INTERVAL_TO_DELTA[normalize_interval(interval)]


def align_timestamp(value: datetime, interval: str) -> datetime:
    dt = ensure_utc(value)
    seconds = int(interval_delta(interval).total_seconds())
    aligned = int(dt.timestamp()) // seconds * seconds
    return datetime.fromtimestamp(aligned, tz=UTC)


def latest_completed_timestamp(interval: str, reference: datetime | None = None) -> datetime:
    current = align_timestamp(reference or utc_now(), interval)
    return current - interval_delta(interval)


def history_window_start(end: datetime, interval: str, retention_bars: int) -> datetime:
    bars = max(retention_bars, 1)
    return ensure_utc(end) - interval_delta(interval) * (bars - 1)
