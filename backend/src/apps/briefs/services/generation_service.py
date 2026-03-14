from __future__ import annotations

from typing import Any

from src.apps.briefs.contracts import BriefGenerationOutput, BriefKind
from src.apps.briefs.language import resolve_requested_language
from src.apps.briefs.prompts import BRIEF_OUTPUT_SCHEMA, load_brief_prompt
from src.apps.briefs.read_models import BriefContextBundle
from src.core.ai import (
    AICapability,
    AIExecutionRequest,
    AIExecutor,
    PydanticOutputValidator,
    get_capability_policy,
)
from src.core.settings import Settings, get_settings


class BriefGenerationService:
    def __init__(self, *, executor: AIExecutor | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._executor = executor or AIExecutor(settings=self._settings)

    async def generate(
        self,
        *,
        bundle: BriefContextBundle,
        context: dict[str, Any],
        requested_provider: str | None = None,
    ) -> dict[str, Any]:
        prompt = load_brief_prompt(bundle.brief_kind)
        merged_context = {**prompt.vars_json, **context}
        policy = get_capability_policy(AICapability.BRIEF_GENERATE, settings=self._settings)
        validator = PydanticOutputValidator(
            contract_name="brief.output.v1",
            schema_contract=BRIEF_OUTPUT_SCHEMA,
            model=BriefGenerationOutput,
            semantic_validator=self._validate_output,
        )
        result = await self._executor.execute(
            AIExecutionRequest(
                capability=AICapability.BRIEF_GENERATE,
                task=str(prompt.task),
                prompt_name=prompt.name,
                prompt_version=int(prompt.version),
                prompt_template=prompt.template,
                context=merged_context,
                validator=validator,
                prompt_vars=dict(prompt.vars_json),
                requested_language=resolve_requested_language(merged_context),
                requested_provider=requested_provider or self._resolve_requested_provider(merged_context),
                preferred_context_format=bundle.preferred_context_format,
                allowed_context_formats=policy.allowed_context_formats,
                allow_degraded_fallback=False,
                source_event_type=f"brief.{bundle.brief_kind.value}",
                source_event_id=bundle.scope_key,
            )
        )
        payload = result.payload
        metadata = result.metadata
        return {
            "title": str(payload.get("title") or ""),
            "summary": str(payload.get("summary") or ""),
            "bullets": [str(item) for item in payload.get("bullets", ())],
            "provider": str(metadata.actual_provider or ""),
            "requested_provider": metadata.requested_provider,
            "model": metadata.model,
            "requested_language": metadata.requested_language,
            "effective_language": metadata.effective_language,
            "context_format": metadata.context_format.value,
            "context_record_count": metadata.context_record_count,
            "context_bytes": metadata.context_bytes,
            "context_token_estimate": metadata.context_token_estimate,
            "fallback_used": metadata.fallback_used,
            "degraded_strategy": metadata.degraded_strategy,
            "latency_ms": metadata.latency_ms,
            "validation_status": metadata.validation_status.value,
            "prompt_name": metadata.prompt_name,
            "prompt_version": int(metadata.prompt_version),
        }

    def _validate_output(self, payload: BriefGenerationOutput, requested_language: str | None, effective_language: str) -> None:
        del requested_language, effective_language
        if not payload.title.strip():
            raise ValueError("Brief title must not be blank.")
        if not payload.summary.strip():
            raise ValueError("Brief summary must not be blank.")
        if len(payload.title.strip()) > 160:
            raise ValueError("Brief title is too long.")
        if len(payload.summary.strip()) > 800:
            raise ValueError("Brief summary is too long.")
        if len(payload.bullets) < 2:
            raise ValueError("Brief must contain at least two bullets.")
        if len(payload.bullets) > 5:
            raise ValueError("Brief must not contain more than five bullets.")
        for bullet in payload.bullets:
            if not str(bullet).strip():
                raise ValueError("Brief bullets must not be blank.")
            if len(str(bullet).strip()) > 180:
                raise ValueError("Brief bullet is too long.")

    def _resolve_requested_provider(self, ctx: dict[str, Any]) -> str | None:
        value = ctx.get("requested_provider")
        if value is None or not str(value).strip():
            return None
        return str(value).strip()


__all__ = ["BriefGenerationService"]
