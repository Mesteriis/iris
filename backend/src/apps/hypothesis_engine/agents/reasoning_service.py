from typing import Any

from src.apps.hypothesis_engine.constants import (
    DEFAULT_HYPOTHESIS_HORIZON_MIN,
    DEFAULT_PROMPT_NAME,
    DEFAULT_TARGET_MOVE,
    EVENT_PROMPT_NAMES,
    PROVIDER_HEURISTIC,
)
from src.apps.hypothesis_engine.contracts import HypothesisGenerationOutput, HypothesisReasoningResult
from src.apps.hypothesis_engine.degraded import build_hypothesis_degraded_output
from src.apps.hypothesis_engine.prompts import HYPOTHESIS_OUTPUT_SCHEMA, PromptLoader
from src.core.ai import (
    AICapability,
    AIExecutionRequest,
    AIExecutor,
    CallableDegradedStrategy,
    PydanticOutputValidator,
    get_capability_policy,
)


class ReasoningService:
    def __init__(self, prompt_loader: PromptLoader, *, executor: AIExecutor | None = None) -> None:
        self._loader = prompt_loader
        self._executor = executor or AIExecutor()

    async def generate(self, ctx: dict[str, Any]) -> HypothesisReasoningResult:
        event_type = str(ctx.get("event_type") or "")
        prompt_name = str(ctx.get("prompt_name") or EVENT_PROMPT_NAMES.get(event_type, DEFAULT_PROMPT_NAME))
        prompt = await self._loader.load(prompt_name)
        merged_ctx = {**prompt.vars_json, **ctx}
        policy = get_capability_policy(AICapability.HYPOTHESIS_GENERATE)
        validator = PydanticOutputValidator(
            contract_name="hypothesis.output.v1",
            schema_contract=HYPOTHESIS_OUTPUT_SCHEMA,
            model=HypothesisGenerationOutput,
        )
        degraded_strategy = CallableDegradedStrategy(
            name=PROVIDER_HEURISTIC,
            handler=self._run_heuristic,
        )
        result = await self._executor.execute(
            AIExecutionRequest(
                capability=AICapability.HYPOTHESIS_GENERATE,
                task=str(prompt.task),
                prompt_name=prompt.name,
                prompt_version=int(prompt.version),
                prompt_template=prompt.template,
                context=merged_ctx,
                validator=validator,
                prompt_vars=dict(prompt.vars_json),
                requested_language=self._resolve_requested_language(ctx),
                requested_provider=self._resolve_requested_provider(ctx),
                preferred_context_format=policy.preferred_context_format,
                allowed_context_formats=policy.allowed_context_formats,
                degraded_strategy=degraded_strategy,
                allow_degraded_fallback=policy.allow_degraded_fallback,
                source_event_type=event_type or None,
                source_event_id=self._string_or_none(ctx.get("event_id")),
                source_stream_id=self._string_or_none(ctx.get("stream_id")),
                causation_id=self._string_or_none(ctx.get("causation_id")),
                correlation_id=self._string_or_none(ctx.get("correlation_id")),
            )
        )
        response = result.payload
        metadata = result.metadata

        assets = [str(asset) for asset in response.get("assets", []) if str(asset).strip()]
        if not assets and ctx.get("symbol") is not None:
            assets = [str(ctx["symbol"])]
        return HypothesisReasoningResult(
            hypothesis_type=str(response.get("type") or "event_follow_through"),
            confidence=max(0.0, min(float(response.get("confidence") or 0.0), 1.0)),
            horizon_min=max(int(response.get("horizon_min") or DEFAULT_HYPOTHESIS_HORIZON_MIN), 1),
            direction=str(response.get("direction") or "neutral"),
            target_move=max(float(response.get("target_move") or DEFAULT_TARGET_MOVE), 0.001),
            summary=str(response.get("summary") or "Event-triggered hypothesis generated."),
            assets=tuple(assets),
            explain=str(response.get("explain") or response.get("summary") or "No explanation provided."),
            kind=str(response.get("kind") or "explain"),
            metadata=metadata,
        )

    async def _run_heuristic(
        self,
        capability: AICapability,
        task: str,
        context: dict[str, Any],
        requested_language: str | None,
        effective_language: str,
    ) -> dict[str, Any]:
        del capability, task, requested_language, effective_language
        return build_hypothesis_degraded_output(context)

    def _resolve_requested_language(self, ctx: dict[str, Any]) -> str | None:
        for key in ("language", "locale"):
            value = ctx.get(key)
            if value is not None and str(value).strip():
                return str(value).strip().lower()
        return None

    def _resolve_requested_provider(self, ctx: dict[str, Any]) -> str | None:
        value = ctx.get("requested_provider")
        if value is None or not str(value).strip():
            return None
        return str(value).strip()

    def _string_or_none(self, value: object) -> str | None:
        if value is None or not str(value).strip():
            return None
        return str(value).strip()
