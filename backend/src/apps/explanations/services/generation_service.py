from typing import Any

from src.apps.explanations.contracts import ExplainKind, ExplanationArtifactResult, ExplanationGenerationOutput
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
from src.core.i18n import MessageDescriptor, get_translation_service, normalize_language
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
    ) -> ExplanationArtifactResult:
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
        title_descriptor = None
        explanation_descriptor = None
        bullet_descriptors: tuple[MessageDescriptor, ...] = ()
        if metadata.fallback_used and metadata.degraded_strategy == TEMPLATE_DEGRADED_STRATEGY:
            title_descriptor, explanation_descriptor, bullet_descriptors = _describe_explanation(bundle.explain_kind, merged_context)
        title = str(payload.get("title") or "")
        explanation = str(payload.get("explanation") or "")
        bullets = tuple(str(item) for item in payload.get("bullets", ()))
        if title_descriptor is not None and explanation_descriptor is not None:
            title = ""
            explanation = ""
            bullets = ()
        return ExplanationArtifactResult(
            title=title,
            explanation=explanation,
            bullets=bullets,
            metadata=metadata,
            title_descriptor=title_descriptor,
            explanation_descriptor=explanation_descriptor,
            bullet_descriptors=bullet_descriptors,
        )

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
    language = normalize_language(effective_language) or "en"
    explain_kind = str(context.get("explain_kind") or "")
    if explain_kind == ExplainKind.DECISION.value:
        return _render_decision_explanation(context, language=language)
    return _render_signal_explanation(context, language=language)


def _render_signal_explanation(context: dict[str, Any], *, language: str) -> dict[str, Any]:
    title_descriptor, explanation_descriptor, bullet_descriptors = _describe_signal_explanation(context)
    translator = get_translation_service()
    title = translator.translate(title_descriptor.key, locale=language, params=dict(title_descriptor.params)).text
    explanation = translator.translate(
        explanation_descriptor.key,
        locale=language,
        params=dict(explanation_descriptor.params),
    ).text
    bullets = [
        translator.translate(descriptor.key, locale=language, params=dict(descriptor.params)).text
        for descriptor in bullet_descriptors
    ]
    return {"title": title, "explanation": explanation, "bullets": bullets[:5]}


def _render_decision_explanation(context: dict[str, Any], *, language: str) -> dict[str, Any]:
    title_descriptor, explanation_descriptor, bullet_descriptors = _describe_decision_explanation(context)
    translator = get_translation_service()
    title = translator.translate(title_descriptor.key, locale=language, params=dict(title_descriptor.params)).text
    explanation = translator.translate(
        explanation_descriptor.key,
        locale=language,
        params=dict(explanation_descriptor.params),
    ).text
    bullets = [
        translator.translate(descriptor.key, locale=language, params=dict(descriptor.params)).text
        for descriptor in bullet_descriptors
    ]
    return {"title": title, "explanation": explanation, "bullets": bullets[:5]}


def _describe_explanation(
    explain_kind: ExplainKind,
    context: dict[str, Any],
) -> tuple[MessageDescriptor, MessageDescriptor, tuple[MessageDescriptor, ...]]:
    if explain_kind is ExplainKind.DECISION:
        return _describe_decision_explanation(context)
    return _describe_signal_explanation(context)


def _describe_signal_explanation(context: dict[str, Any]) -> tuple[MessageDescriptor, MessageDescriptor, tuple[MessageDescriptor, ...]]:
    symbol = str(context.get("symbol") or "asset").upper()
    timeframe = int(context.get("timeframe") or 0)
    signal_type = str(context.get("signal_type") or "signal").replace("_", " ")
    confidence = float(context.get("confidence") or 0.0)
    priority_score = float(context.get("priority_score") or 0.0)
    context_score = float(context.get("context_score") or 0.0)
    regime_alignment = float(context.get("regime_alignment") or 0.0)
    regime = str(context.get("market_regime") or "").strip()
    cycle_phase = str(context.get("cycle_phase") or "").strip()
    clusters = [str(item) for item in context.get("cluster_membership", ()) if str(item).strip()]
    params = {
        "symbol": symbol,
        "timeframe": timeframe,
        "signal_type": signal_type,
        "confidence": confidence,
        "priority_score": priority_score,
        "context_score": context_score,
        "regime_alignment": regime_alignment,
        "market_regime": regime,
        "cycle_phase": cycle_phase,
        "cluster_membership": ", ".join(clusters[:3]),
    }
    bullets = [
        MessageDescriptor(key="brief.explanation.signal.bullet.priority", params=params),
        MessageDescriptor(key="brief.explanation.signal.bullet.context", params=params),
    ]
    if regime:
        bullets.append(MessageDescriptor(key="brief.explanation.signal.bullet.market_regime", params=params))
    if cycle_phase:
        bullets.append(MessageDescriptor(key="brief.explanation.signal.bullet.cycle_phase", params=params))
    if clusters:
        bullets.append(MessageDescriptor(key="brief.explanation.signal.bullet.cluster_membership", params=params))
    return (
        MessageDescriptor(key="brief.explanation.signal.title", params=params),
        MessageDescriptor(key="brief.explanation.signal.body", params=params),
        tuple(bullets[:5]),
    )


def _describe_decision_explanation(context: dict[str, Any]) -> tuple[MessageDescriptor, MessageDescriptor, tuple[MessageDescriptor, ...]]:
    symbol = str(context.get("symbol") or "asset").upper()
    timeframe = int(context.get("timeframe") or 0)
    decision = str(context.get("decision") or "hold").upper()
    confidence = float(context.get("confidence") or 0.0)
    score = float(context.get("score") or 0.0)
    reason = str(context.get("reason") or "").strip()
    sector = str(context.get("sector") or "").strip()
    params = {
        "symbol": symbol,
        "timeframe": timeframe,
        "decision": decision,
        "confidence": confidence,
        "score": score,
        "reason": reason,
        "sector": sector,
    }
    bullets = [
        MessageDescriptor(
            key=(
                "brief.explanation.decision.bullet.machine_reason"
                if reason
                else "brief.explanation.decision.bullet.machine_reason_missing"
            ),
            params=params,
        ),
        MessageDescriptor(key="brief.explanation.decision.bullet.confidence_score", params=params),
    ]
    if sector:
        bullets.append(MessageDescriptor(key="brief.explanation.decision.bullet.sector", params=params))
    return (
        MessageDescriptor(key="brief.explanation.decision.title", params=params),
        MessageDescriptor(key="brief.explanation.decision.body", params=params),
        tuple(bullets[:5]),
    )


__all__ = ["ExplanationGenerationService", "TEMPLATE_DEGRADED_STRATEGY", "render_deterministic_explanation"]
