from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder

from src.apps.explanations.contracts import ExplainKind, ExplanationGenerationResult, ExplanationGenerationStatus
from src.apps.explanations.language import resolve_effective_language
from src.apps.explanations.models import AIExplanation
from src.apps.explanations.query_services import ExplanationQueryService
from src.apps.explanations.read_models import ExplanationContextBundle
from src.apps.explanations.repositories import ExplanationRepository
from src.apps.explanations.services.generation_service import ExplanationGenerationService
from src.apps.hypothesis_engine.prompts import PromptLoader
from src.apps.hypothesis_engine.query_services import HypothesisQueryService
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork


class ExplanationService(PersistenceComponent):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="explanations",
            component_name="ExplanationService",
        )
        self._uow = uow
        self._repo = ExplanationRepository(uow.session)
        self._queries = ExplanationQueryService(uow.session)
        self._prompt_loader = PromptLoader(HypothesisQueryService(uow.session))
        self._generator = ExplanationGenerationService()

    async def generate_and_store(
        self,
        *,
        explain_kind: ExplainKind,
        subject_id: int,
        language: str | None = None,
        requested_provider: str | None = None,
        force: bool = False,
    ) -> ExplanationGenerationResult:
        bundle = await self._load_context_bundle(explain_kind=explain_kind, subject_id=subject_id)
        context = dict(bundle.context)
        if language is not None and str(language).strip():
            context["language"] = str(language).strip()
        if requested_provider is not None and str(requested_provider).strip():
            context["requested_provider"] = str(requested_provider).strip()
        effective_language = resolve_effective_language(context)
        existing = await self._repo.get_by_subject(
            explain_kind=explain_kind,
            subject_id=int(subject_id),
            language=effective_language,
        )
        if existing is not None and not force and _same_subject_snapshot(existing.subject_updated_at, bundle.subject_updated_at):
            self._log_debug(
                "service.generate_explanation.skip_current",
                mode="write",
                explain_kind=explain_kind.value,
                subject_id=int(subject_id),
                language=effective_language,
                explanation_id=int(existing.id),
            )
            return ExplanationGenerationResult(
                status=ExplanationGenerationStatus.SKIPPED,
                reason="explanation_already_current",
                explanation_id=int(existing.id),
                explain_kind=explain_kind,
                subject_id=int(subject_id),
                language=effective_language,
                symbol=bundle.symbol,
                generated_at=existing.updated_at,
                subject_updated_at=existing.subject_updated_at,
            )

        prompt = await self._prompt_loader.load(f"explain.{explain_kind.value}")
        generated = await self._generator.generate(
            bundle=bundle,
            prompt=prompt,
            context=context,
            requested_provider=requested_provider,
        )
        item = await self._repo.upsert_explanation(
            existing=existing,
            payload={
                "explain_kind": explain_kind.value,
                "subject_id": int(subject_id),
                "coin_id": bundle.coin_id,
                "symbol": bundle.symbol,
                "timeframe": bundle.timeframe,
                "language": str(generated["effective_language"]),
                "title": str(generated["title"]),
                "explanation": str(generated["explanation"]),
                "bullets_json": [str(row) for row in generated["bullets"]],
                "refs_json": jsonable_encoder(bundle.refs_json),
                "context_json": jsonable_encoder(
                    {
                        "snapshot": bundle.context,
                        "ai_execution": {
                            "requested_provider": generated.get("requested_provider"),
                            "requested_language": generated.get("requested_language"),
                            "effective_language": generated.get("effective_language"),
                            "context_format": generated.get("context_format"),
                            "context_record_count": generated.get("context_record_count"),
                            "context_bytes": generated.get("context_bytes"),
                            "context_token_estimate": generated.get("context_token_estimate"),
                            "fallback_used": generated.get("fallback_used"),
                            "degraded_strategy": generated.get("degraded_strategy"),
                            "latency_ms": generated.get("latency_ms"),
                            "validation_status": generated.get("validation_status"),
                        },
                    }
                ),
                "provider": str(generated["provider"]),
                "model": str(generated["model"]),
                "prompt_name": str(generated["prompt_name"]),
                "prompt_version": int(generated["prompt_version"]),
                "subject_updated_at": bundle.subject_updated_at,
            },
        )
        return self._result_contract(item=item)

    async def _load_context_bundle(self, *, explain_kind: ExplainKind, subject_id: int) -> ExplanationContextBundle:
        if explain_kind is ExplainKind.SIGNAL:
            bundle = await self._queries.build_signal_context(subject_id)
        elif explain_kind is ExplainKind.DECISION:
            bundle = await self._queries.build_decision_context(subject_id)
        else:
            raise ValueError(f"Unsupported explain kind '{explain_kind.value}'.")
        if bundle is None:
            raise LookupError(f"Subject '{explain_kind.value}:{int(subject_id)}' is not available.")
        return bundle

    def _result_contract(self, *, item: AIExplanation) -> ExplanationGenerationResult:
        return ExplanationGenerationResult(
            status=ExplanationGenerationStatus.OK,
            explanation_id=int(item.id),
            explain_kind=ExplainKind(str(item.explain_kind)),
            subject_id=int(item.subject_id),
            language=str(item.language),
            symbol=str(item.symbol) if item.symbol is not None else None,
            generated_at=item.updated_at,
            subject_updated_at=item.subject_updated_at,
        )


def _same_subject_snapshot(left, right) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    return left == right


__all__ = ["ExplanationService"]
