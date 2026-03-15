from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.core.ai.telemetry import AIExecutionMetadata


class HypothesisGenerationOutput(BaseModel):
    type: str
    confidence: float = Field(ge=0.0, le=1.0)
    horizon_min: int = Field(ge=1)
    direction: Literal["up", "down", "neutral"]
    target_move: float = Field(gt=0.0)
    summary: str
    assets: list[str] = Field(min_length=1)
    explain: str | None = None
    kind: str | None = None

    @field_validator("assets")
    @classmethod
    def normalize_assets(cls, value: list[str]) -> list[str]:
        assets = [str(item).strip() for item in value if str(item).strip()]
        if not assets:
            raise ValueError("At least one asset must be present in the hypothesis output.")
        return assets


class HypothesisCreationStatus(StrEnum):
    CREATED = "created"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class PromptCacheInvalidation:
    name: str


@dataclass(frozen=True, slots=True)
class PromptRecord:
    id: int
    name: str
    task: str
    version: int
    veil_lifted: bool
    is_active: bool
    template: str
    vars_json: dict[str, object] = field(default_factory=dict)
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PromptMutationResult:
    prompt: PromptRecord
    cache_invalidations: tuple[PromptCacheInvalidation, ...] = ()


@dataclass(frozen=True, slots=True)
class HypothesisPendingEvent:
    event_type: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HypothesisReasoningResult:
    hypothesis_type: str
    confidence: float
    horizon_min: int
    direction: str
    target_move: float
    summary: str
    assets: tuple[str, ...]
    explain: str
    kind: str
    metadata: AIExecutionMetadata


@dataclass(frozen=True, slots=True)
class HypothesisCreationResult:
    status: HypothesisCreationStatus
    hypothesis_id: int | None = None
    reason: str | None = None
    pending_events: tuple[HypothesisPendingEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class HypothesisEvaluationBatchResult:
    evaluation_ids: tuple[int, ...] = ()
    pending_events: tuple[HypothesisPendingEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class WeightUpdateResult:
    updated: bool
    pending_events: tuple[HypothesisPendingEvent, ...] = ()


__all__ = [
    "HypothesisCreationResult",
    "HypothesisCreationStatus",
    "HypothesisEvaluationBatchResult",
    "HypothesisGenerationOutput",
    "HypothesisPendingEvent",
    "HypothesisReasoningResult",
    "PromptCacheInvalidation",
    "PromptMutationResult",
    "PromptRecord",
    "WeightUpdateResult",
]
