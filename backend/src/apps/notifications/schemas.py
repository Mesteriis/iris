from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NotificationRead(BaseModel):
    id: int
    coin_id: int
    symbol: str | None = None
    sector: str | None = None
    timeframe: int
    title: str
    content_kind: str
    rendered_locale: str | None = None
    title_key: str | None = None
    title_params: dict[str, Any] = Field(default_factory=dict)
    message: str
    message_key: str | None = None
    message_params: dict[str, Any] = Field(default_factory=dict)
    severity: str
    urgency: str
    content_json: Any
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
