from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from iris.core.ai.telemetry import AIExecutionMetadata
from iris.core.i18n import MessageDescriptor


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
    rendered_locale: str
    symbol: str | None = None
    reason: str | None = None
    generated_at: datetime | None = None
    subject_updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ExplanationArtifactResult:
    title: str
    explanation: str
    bullets: tuple[str, ...]
    metadata: AIExecutionMetadata
    title_descriptor: MessageDescriptor | None = None
    explanation_descriptor: MessageDescriptor | None = None
    bullet_descriptors: tuple[MessageDescriptor, ...] = ()


__all__ = [
    "ExplainKind",
    "ExplanationArtifactResult",
    "ExplanationGenerationOutput",
    "ExplanationGenerationResult",
    "ExplanationGenerationStatus",
]
