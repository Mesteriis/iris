from dataclasses import dataclass
from typing import Any

from src.core.ai.contracts import AICapability, AIContextFormat, AIValidationStatus


@dataclass(frozen=True, slots=True)
class AIExecutionMetadata:
    capability: AICapability
    task: str
    requested_provider: str | None
    actual_provider: str | None
    model: str
    requested_language: str | None
    effective_language: str
    context_format: AIContextFormat
    context_record_count: int
    context_bytes: int
    context_token_estimate: int | None
    fallback_used: bool
    degraded_strategy: str | None
    latency_ms: int
    validation_status: AIValidationStatus
    prompt_name: str
    prompt_version: int
    source_event_type: str | None = None
    source_event_id: str | None = None
    source_stream_id: str | None = None
    causation_id: str | None = None
    correlation_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability.value,
            "task": self.task,
            "requested_provider": self.requested_provider,
            "actual_provider": self.actual_provider,
            "model": self.model,
            "requested_language": self.requested_language,
            "effective_language": self.effective_language,
            "context_format": self.context_format.value,
            "context_record_count": self.context_record_count,
            "context_bytes": self.context_bytes,
            "context_token_estimate": self.context_token_estimate,
            "fallback_used": self.fallback_used,
            "degraded_strategy": self.degraded_strategy,
            "latency_ms": self.latency_ms,
            "validation_status": self.validation_status.value,
            "prompt_name": self.prompt_name,
            "prompt_version": self.prompt_version,
            "source_event_type": self.source_event_type,
            "source_event_id": self.source_event_id,
            "source_stream_id": self.source_stream_id,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True, slots=True)
class AIExecutionResult:
    payload: dict[str, Any]
    metadata: AIExecutionMetadata


__all__ = ["AIExecutionMetadata", "AIExecutionResult"]
