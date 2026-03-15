from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ExplainKind(StrEnum):
    SIGNAL = "signal"
    DECISION = "decision"


class ExplanationGenerationStatus(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"


class ExplanationGenerationOutput(BaseModel):
    title: str
    explanation: str
    bullets: list[str]

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True, slots=True)
class ExplanationGenerationResult:
    status: ExplanationGenerationStatus
    explanation_id: int
    explain_kind: ExplainKind
    subject_id: int
    language: str
    symbol: str | None = None
    reason: str | None = None
    generated_at: datetime | None = None
    subject_updated_at: datetime | None = None


__all__ = [
    "ExplainKind",
    "ExplanationGenerationOutput",
    "ExplanationGenerationResult",
    "ExplanationGenerationStatus",
]
