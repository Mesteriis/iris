from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from src.apps.explanations.contracts import ExplainKind
from src.core.http.contracts import AnalyticalReadContract


class ExplanationRead(AnalyticalReadContract):
    id: int
    explain_kind: ExplainKind
    subject_id: int
    coin_id: int | None = None
    symbol: str | None = None
    timeframe: int | None = None
    title: str
    content_kind: str
    rendered_locale: str | None = None
    title_key: str | None = None
    title_params: dict[str, Any] = Field(default_factory=dict)
    explanation: str
    explanation_key: str | None = None
    explanation_params: dict[str, Any] = Field(default_factory=dict)
    bullets: list[str]
    bullet_keys: list[str] = Field(default_factory=list)
    bullet_params: list[dict[str, Any]] = Field(default_factory=list)
    content_json: Any
    refs_json: Any
    context_json: Any
    provider: str
    model: str
    prompt_name: str
    prompt_version: int
    subject_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


__all__ = ["ExplanationRead"]
