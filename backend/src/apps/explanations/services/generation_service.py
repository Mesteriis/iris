from __future__ import annotations

from typing import Any

from src.apps.explanations.contracts import ExplainKind, ExplanationGenerationOutput
from src.apps.explanations.language import resolve_requested_language
from src.apps.explanations.prompts import EXPLAIN_OUTPUT_SCHEMA
from src.apps.explanations.read_models import ExplanationContextBundle
from src.apps.hypothesis_engine.prompts import LoadedPrompt
from src.core.ai import (
    AICapability,
    AIExecutionRequest,
    AIExecutor,
    CallableDegradedStrategy,
    PydanticOutputValidator,
    get_capability_policy,
)
from src.core.settings import Settings, get_settings

TEMPLATE_DEGRADED_STRATEGY = "deterministic_explain_summary"


class ExplanationGenerationService:
    def __init__(self, *, executor: AIExecutor | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._executor = executor or AIExecutor(settings=self._settings)

    async def generate(
        self,
        *,
        bundle: ExplanationContextBundle,
        prompt: LoadedPrompt,
        context: dict[str, Any],
        requested_provider: str | None = None,
    ) -> dict[str, Any]:
        merged_context = {**prompt.vars_json, **context}
        policy = get_capability_policy(AICapability.EXPLAIN_GENERATE, settings=self._settings)
        validator = PydanticOutputValidator(
            contract_name="explain.output.v1",
            schema_contract=EXPLAIN_OUTPUT_SCHEMA,
            model=ExplanationGenerationOutput,
            semantic_validator=self._validate_output,
        )
        degraded_strategy = CallableDegradedStrategy(
            name=TEMPLATE_DEGRADED_STRATEGY,
            handler=self._run_deterministic_fallback,
        )
        result = await self._executor.execute(
            AIExecutionRequest(
                capability=AICapability.EXPLAIN_GENERATE,
                task=str(prompt.task),
                prompt_name=prompt.name,
                prompt_version=int(prompt.version),
                prompt_template=prompt.template,
                context=merged_context,
                validator=validator,
                prompt_vars=dict(prompt.vars_json),
                requested_language=resolve_requested_language(merged_context),
                requested_provider=requested_provider or self._resolve_requested_provider(merged_context),
                preferred_context_format=policy.preferred_context_format,
                allowed_context_formats=policy.allowed_context_formats,
                degraded_strategy=degraded_strategy,
                allow_degraded_fallback=policy.allow_degraded_fallback,
                source_event_type=f"explain.{bundle.explain_kind.value}",
                source_event_id=str(bundle.subject_id),
            )
        )
        payload = result.payload
        metadata = result.metadata
        return {
            "title": str(payload.get("title") or ""),
            "explanation": str(payload.get("explanation") or ""),
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

    def _validate_output(self, payload: ExplanationGenerationOutput, requested_language: str | None, effective_language: str) -> None:
        del requested_language, effective_language
        if not payload.title.strip():
            raise ValueError("Explanation title must not be blank.")
        if not payload.explanation.strip():
            raise ValueError("Explanation body must not be blank.")
        if len(payload.title.strip()) > 160:
            raise ValueError("Explanation title is too long.")
        if len(payload.explanation.strip()) > 900:
            raise ValueError("Explanation body is too long.")
        if len(payload.bullets) < 2:
            raise ValueError("Explanation must contain at least two bullets.")
        if len(payload.bullets) > 5:
            raise ValueError("Explanation must not contain more than five bullets.")
        for bullet in payload.bullets:
            if not str(bullet).strip():
                raise ValueError("Explanation bullets must not be blank.")
            if len(str(bullet).strip()) > 200:
                raise ValueError("Explanation bullet is too long.")

    async def _run_deterministic_fallback(
        self,
        capability: AICapability,
        task: str,
        context: dict[str, Any],
        requested_language: str | None,
        effective_language: str,
    ) -> dict[str, Any]:
        del capability, task, requested_language
        return render_deterministic_explanation(context, effective_language=effective_language)

    def _resolve_requested_provider(self, ctx: dict[str, Any]) -> str | None:
        value = ctx.get("requested_provider")
        if value is None or not str(value).strip():
            return None
        return str(value).strip()


def render_deterministic_explanation(context: dict[str, Any], *, effective_language: str) -> dict[str, Any]:
    language = (effective_language or "en").strip().lower()
    explain_kind = str(context.get("explain_kind") or "")
    if explain_kind == ExplainKind.DECISION.value:
        return _render_decision_explanation(context, language=language)
    return _render_signal_explanation(context, language=language)


def _render_signal_explanation(context: dict[str, Any], *, language: str) -> dict[str, Any]:
    symbol = str(context.get("symbol") or "asset").upper()
    timeframe = int(context.get("timeframe") or 0)
    signal_type = str(context.get("signal_type") or "signal").replace("_", " ")
    confidence = float(context.get("confidence") or 0.0)
    regime = str(context.get("market_regime") or "").strip()
    cycle_phase = str(context.get("cycle_phase") or "").strip()
    clusters = [str(item) for item in context.get("cluster_membership", ()) if str(item).strip()]
    if language.startswith("ru"):
        title = f"{symbol}: объяснение сигнала"
        explanation = (
            f"Сигнал {signal_type} на таймфрейме {timeframe}м появился с уверенностью {confidence:.2f}. "  # noqa: RUF001
            f"Это каноническое наблюдение, а не подтвержденное действие."  # noqa: RUF001
        )
        bullets = [
            f"Приоритет сигнала: {float(context.get('priority_score') or 0.0):.2f}.",
            f"Контекстный скор: {float(context.get('context_score') or 0.0):.2f}, выравнивание с режимом: {float(context.get('regime_alignment') or 0.0):.2f}.",  # noqa: RUF001
        ]
        if regime:
            bullets.append(f"Рыночный режим в snapshot: {regime}.")
        if cycle_phase:
            bullets.append(f"Фаза цикла: {cycle_phase}.")
        if clusters:
            bullets.append(f"Кластерные сигналы: {', '.join(clusters[:3])}.")
        return {"title": title, "explanation": explanation, "bullets": bullets[:5]}
    title = f"{symbol}: signal explanation"
    explanation = (
        f"The {signal_type} signal on {timeframe}m was recorded with confidence {confidence:.2f}. "
        f"This is a canonical observation, not an executed action."
    )
    bullets = [
        f"Priority score is {float(context.get('priority_score') or 0.0):.2f}.",
        f"Context score is {float(context.get('context_score') or 0.0):.2f} and regime alignment is {float(context.get('regime_alignment') or 0.0):.2f}.",
    ]
    if regime:
        bullets.append(f"Market regime snapshot: {regime}.")
    if cycle_phase:
        bullets.append(f"Cycle phase snapshot: {cycle_phase}.")
    if clusters:
        bullets.append(f"Cluster membership flags: {', '.join(clusters[:3])}.")
    return {"title": title, "explanation": explanation, "bullets": bullets[:5]}


def _render_decision_explanation(context: dict[str, Any], *, language: str) -> dict[str, Any]:
    symbol = str(context.get("symbol") or "asset").upper()
    timeframe = int(context.get("timeframe") or 0)
    decision = str(context.get("decision") or "hold").upper()
    confidence = float(context.get("confidence") or 0.0)
    score = float(context.get("score") or 0.0)
    reason = str(context.get("reason") or "").strip()
    if language.startswith("ru"):
        title = f"{symbol}: объяснение решения"
        explanation = (
            f"Решение {decision} для таймфрейма {timeframe}м было сохранено с уверенностью {confidence:.2f} и score {score:.2f}. "  # noqa: RUF001
            f"Это канонический artifact решения, а не персональная рекомендация."  # noqa: RUF001
        )
        bullets = [
            f"Machine reason: {reason or 'причина не указана'}.",
            f"Confidence/score snapshot: {confidence:.2f} / {score:.2f}.",
        ]
        if context.get("sector"):
            bullets.append(f"Сектор актива: {context['sector']}.")
        return {"title": title, "explanation": explanation, "bullets": bullets[:5]}
    title = f"{symbol}: decision explanation"
    explanation = (
        f"The {decision} decision for {timeframe}m was stored with confidence {confidence:.2f} and score {score:.2f}. "
        f"It is a canonical decision artifact, not personalized advice."
    )
    bullets = [
        f"Machine reason: {reason or 'no reason provided'}.",
        f"Confidence and score snapshot: {confidence:.2f} / {score:.2f}.",
    ]
    if context.get("sector"):
        bullets.append(f"Sector context: {context['sector']}.")
    return {"title": title, "explanation": explanation, "bullets": bullets[:5]}


__all__ = ["ExplanationGenerationService", "TEMPLATE_DEGRADED_STRATEGY", "render_deterministic_explanation"]
