import csv
import io
import json
from time import perf_counter
from typing import Any

from src.core.ai.capabilities import get_capability_policy
from src.core.ai.contracts import AICapability, AIContextFormat, AIExecutionRequest, AIValidationStatus
from src.core.ai.provider_registry import AIProviderRegistry, build_provider_registry
from src.core.ai.telemetry import AIExecutionMetadata, AIExecutionResult
from src.core.ai.validators import AIPayloadValidationError
from src.core.settings import Settings, get_settings


class AIExecutionError(RuntimeError):
    def __init__(self, message: str, *, validation_status: AIValidationStatus = AIValidationStatus.REJECTED) -> None:
        super().__init__(message)
        self.validation_status = validation_status


class AICapabilityUnavailableError(AIExecutionError):
    pass


def _compact_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _compact_json_value(item)
            for key, item in value.items()
            if item not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_compact_json_value(item) for item in value if item not in (None, "", [], {})]
    return value


def _tabular_rows(context: dict[str, Any]) -> list[dict[str, Any]] | None:
    rows = context.get("rows")
    if isinstance(rows, list) and all(isinstance(item, dict) for item in rows):
        return [dict(item) for item in rows]
    for value in context.values():
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            return [dict(item) for item in value]
    return None


def _serialize_context(context: dict[str, Any], format_name: AIContextFormat) -> str:
    if format_name is AIContextFormat.JSON:
        return json.dumps(context, ensure_ascii=True, sort_keys=True, default=str)
    if format_name is AIContextFormat.COMPACT_JSON:
        return json.dumps(_compact_json_value(context), ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":"))
    rows = _tabular_rows(context)
    if rows is None:
        raise AIExecutionError(f"Context format '{format_name.value}' requires row-like objects in context.")
    columns = sorted({str(key) for row in rows for key in row})
    if format_name is AIContextFormat.TOON:
        lines = [",".join(columns)]
        lines.extend(
            ",".join(json.dumps(row.get(column), ensure_ascii=True, default=str) for column in columns)
            for row in rows
        )
        return "\n".join(lines)
    if format_name is AIContextFormat.CSV:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in columns})
        return buffer.getvalue()
    raise AIExecutionError(f"Unsupported context format '{format_name.value}'.")


def _select_context_format(request: AIExecutionRequest) -> AIContextFormat:
    preferred = request.preferred_context_format
    if preferred in request.allowed_context_formats:
        return preferred
    return request.allowed_context_formats[0]


def _count_context_records(context: dict[str, Any]) -> int:
    rows = _tabular_rows(context)
    if rows is not None:
        return len(rows)
    payload = context.get("payload")
    if isinstance(payload, dict):
        return len(payload)
    return len(context)


def _estimate_tokens(text: str) -> int:
    return max(len(text.encode("utf-8")) // 4, 1)


class AIExecutor:
    def __init__(self, *, settings: Settings | None = None, registry: AIProviderRegistry | None = None) -> None:
        self._settings = settings or get_settings()
        self._registry = registry or build_provider_registry(self._settings)

    def _resolve_language(self, requested_language: str | None) -> str:
        if requested_language:
            return str(requested_language).strip().lower()
        default_language = getattr(self._settings.language, "value", self._settings.language)
        return str(default_language or "en").strip().lower() or "en"

    async def execute(self, request: AIExecutionRequest) -> AIExecutionResult:
        policy = get_capability_policy(request.capability, settings=self._settings)
        effective_language = self._resolve_language(request.requested_language)
        if not self._registry.has_real_provider_for(request.capability):
            raise AICapabilityUnavailableError(
                f"Capability '{request.capability.value}' has no configured provider.",
            )
        context_format = _select_context_format(request)
        serialized_context = _serialize_context(request.context, context_format)
        context_bytes = len(serialized_context.encode("utf-8"))
        started_at = perf_counter()
        requested_provider = request.requested_provider
        provider_config = self._registry.resolve(
            capability=request.capability,
            requested_provider=request.requested_provider,
        )
        provider = self._registry.instantiate(provider_config)
        fallback_used = False
        degraded_strategy_name: str | None = None
        validation_status = AIValidationStatus.VALID
        actual_provider = provider_config.name
        model = provider_config.model
        try:
            raw_payload = await provider.generate_structured(
                prompt=request.prompt_template,
                serialized_context=serialized_context,
                context_format=context_format,
                schema_contract=request.validator.schema_contract,
                requested_language=request.requested_language,
                effective_language=effective_language,
            )
            payload = request.validator.validate(
                raw_payload,
                requested_language=request.requested_language,
                effective_language=effective_language,
            )
        except Exception as exc:
            can_fallback = policy.allow_degraded_fallback and request.allow_degraded_fallback and request.degraded_strategy is not None
            if not can_fallback:
                if isinstance(exc, AIPayloadValidationError):
                    raise AIExecutionError(str(exc), validation_status=exc.status) from exc
                raise AIExecutionError(str(exc)) from exc
            degraded_strategy_name = request.degraded_strategy.name
            fallback_used = True
            validation_status = AIValidationStatus.FALLBACK_APPLIED
            actual_provider = degraded_strategy_name
            model = f"degraded:{degraded_strategy_name}"
            degraded_payload = await request.degraded_strategy.execute(
                capability=request.capability,
                task=request.task,
                context=request.context,
                requested_language=request.requested_language,
                effective_language=effective_language,
            )
            payload = request.validator.validate(
                degraded_payload,
                requested_language=request.requested_language,
                effective_language=effective_language,
            )
        latency_ms = int((perf_counter() - started_at) * 1000)
        return AIExecutionResult(
            payload=payload,
            metadata=AIExecutionMetadata(
                capability=request.capability,
                task=request.task,
                requested_provider=requested_provider,
                actual_provider=actual_provider,
                model=model,
                requested_language=request.requested_language,
                effective_language=effective_language,
                context_format=context_format,
                context_record_count=_count_context_records(request.context),
                context_bytes=context_bytes,
                context_token_estimate=_estimate_tokens(serialized_context),
                fallback_used=fallback_used,
                degraded_strategy=degraded_strategy_name,
                latency_ms=latency_ms,
                validation_status=validation_status,
                prompt_name=request.prompt_name,
                prompt_version=request.prompt_version,
                source_event_type=request.source_event_type,
                source_event_id=request.source_event_id,
                source_stream_id=request.source_stream_id,
                causation_id=request.causation_id,
                correlation_id=request.correlation_id,
            ),
        )


__all__ = ["AICapabilityUnavailableError", "AIExecutionError", "AIExecutor"]
