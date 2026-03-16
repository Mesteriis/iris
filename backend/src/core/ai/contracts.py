from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from src.core.http.launch_modes import DeploymentProfile


class AICapability(StrEnum):
    HYPOTHESIS_GENERATE = "hypothesis_generate"
    NOTIFICATION_HUMANIZE = "notification_humanize"
    BRIEF_GENERATE = "brief_generate"
    EXPLAIN_GENERATE = "explain_generate"


class AIProviderKind(StrEnum):
    OPENAI_LIKE = "openai_like"
    LOCAL_HTTP = "local_http"


class AIContextFormat(StrEnum):
    JSON = "json"
    COMPACT_JSON = "compact_json"
    TOON = "toon"
    CSV = "csv"


class AIValidationStatus(StrEnum):
    VALID = "valid"
    INVALID_SCHEMA = "invalid_schema"
    INVALID_SEMANTICS = "invalid_semantics"
    FALLBACK_APPLIED = "fallback_applied"
    REJECTED = "rejected"


class AIHealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass(frozen=True, slots=True)
class AIProviderConfig:
    name: str
    kind: AIProviderKind
    enabled: bool
    base_url: str
    endpoint: str
    auth_token: str | None
    auth_header: str
    auth_scheme: str | None
    model: str
    timeout_seconds: float
    priority: int
    capabilities: tuple[AICapability, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    max_context_tokens: int | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class AICapabilityPolicy:
    capability: AICapability
    enabled: bool
    allow_degraded_fallback: bool
    preferred_context_format: AIContextFormat
    allowed_context_formats: tuple[AIContextFormat, ...]


class AIOutputValidator(Protocol):
    contract_name: str
    schema_contract: dict[str, Any] | str

    def validate(
        self,
        payload: dict[str, Any],
        *,
        requested_language: str | None,
        effective_language: str,
    ) -> dict[str, Any]: ...


class AIDegradedStrategy(Protocol):
    @property
    def name(self) -> str: ...

    async def execute(
        self,
        *,
        capability: AICapability,
        task: str,
        context: dict[str, Any],
        requested_language: str | None,
        effective_language: str,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class AIExecutionRequest:
    capability: AICapability
    task: str
    prompt_name: str
    prompt_version: int
    prompt_template: str
    context: dict[str, Any]
    validator: AIOutputValidator
    prompt_vars: dict[str, Any] = field(default_factory=dict)
    requested_language: str | None = None
    requested_provider: str | None = None
    preferred_context_format: AIContextFormat = AIContextFormat.JSON
    allowed_context_formats: tuple[AIContextFormat, ...] = (AIContextFormat.JSON,)
    degraded_strategy: AIDegradedStrategy | None = None
    allow_degraded_fallback: bool = False
    source_event_type: str | None = None
    source_event_id: str | None = None
    source_stream_id: str | None = None
    causation_id: str | None = None
    correlation_id: str | None = None


AI_OPERATOR_PROFILES: tuple[DeploymentProfile, ...] = (
    DeploymentProfile.PLATFORM_FULL,
    DeploymentProfile.PLATFORM_LOCAL,
)


__all__ = [
    "AI_OPERATOR_PROFILES",
    "AICapability",
    "AICapabilityPolicy",
    "AIContextFormat",
    "AIDegradedStrategy",
    "AIExecutionRequest",
    "AIHealthState",
    "AIOutputValidator",
    "AIProviderConfig",
    "AIProviderKind",
    "AIValidationStatus",
]
