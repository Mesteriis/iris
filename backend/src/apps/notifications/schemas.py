from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    id: int
    coin_id: int
    symbol: str | None = None
    sector: str | None = None
    timeframe: int
    title: str
    message: str
    severity: str
    urgency: str
    language: str
    refs_json: Any
    context_json: Any
    provider: str
    model: str
    prompt_name: str
    prompt_version: int
    source_event_type: str
    source_event_id: str
    source_stream_id: str | None = None
    causation_id: str | None = None
    correlation_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


__all__ = ["NotificationRead"]
