from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict

from src.apps.explanations.contracts import ExplainKind
from src.core.http.contracts import AnalyticalReadContract


class ExplanationRead(AnalyticalReadContract):
    id: int
    explain_kind: ExplainKind
    subject_id: int
    coin_id: int | None = None
    symbol: str | None = None
    timeframe: int | None = None
    language: str
    title: str
    explanation: str
    bullets: list[str]
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
