from datetime import datetime

from pydantic import BaseModel


class SourceStatusRead(BaseModel):
    name: str
    asset_types: list[str]
    supported_intervals: list[str]
    official_limit: bool
    rate_limited: bool
    cooldown_seconds: float
    next_available_at: datetime | None
    requests_per_window: int | None = None
    window_seconds: int | None = None
    min_interval_seconds: float | None = None
    request_cost: int | None = None
    fallback_retry_after_seconds: int | None = None


class SystemStatusRead(BaseModel):
    service: str
    status: str
    taskiq_mode: str
    taskiq_running: bool
    sources: list[SourceStatusRead]
