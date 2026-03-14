from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ExplainKind(StrEnum):
    SIGNAL = "signal"
    DECISION = "decision"


class ExplanationGenerationOutput(BaseModel):
    title: str
    explanation: str
    bullets: list[str]

    model_config = ConfigDict(extra="forbid")


__all__ = ["ExplainKind", "ExplanationGenerationOutput"]
