from datetime import datetime
from typing import Any

from iris.apps.briefs.contracts import BriefArtifactResult, BriefGenerationResult, BriefGenerationStatus, BriefKind
from iris.apps.briefs.language import resolve_effective_language
from iris.apps.briefs.models import AIBrief
from iris.apps.briefs.query_services import BriefQueryService
from iris.apps.briefs.read_models import BriefContextBundle
from iris.apps.briefs.repositories import BriefRepository
from iris.apps.briefs.services.generation_service import BriefGenerationService
from iris.apps.hypothesis_engine.prompts import PromptLoader
from iris.apps.hypothesis_engine.query_services import HypothesisQueryService
from iris.core.db.persistence import PersistenceComponent, to_jsonable_data
from iris.core.db.uow import BaseAsyncUnitOfWork
from iris.core.errors import ResourceNotFoundError, ValidationFailedError
from iris.core.i18n import CONTENT_KIND_GENERATED_TEXT, build_generated_text_content, content_rendered_locale


class BriefService(PersistenceComponent):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="briefs",
            component_name="BriefService",
        )
        self._uow = uow
        self._repo = BriefRepository(uow.session)
        self._queries = BriefQueryService(uow.session)
        self._prompt_loader = PromptLoader(HypothesisQueryService(uow.session))
        self._generator = BriefGenerationService()

    async def generate_and_store(
        self,
        *,
        brief_kind: BriefKind,
        symbol: str | None = None,
        requested_provider: str | None = None,
        force: bool = False,
    ) -> BriefGenerationResult:
        bundle = await self._load_context_bundle(brief_kind=brief_kind, symbol=symbol)
        context = dict(bundle.context)
        if requested_provider is not None and str(requested_provider).strip():
            context["requested_provider"] = str(requested_provider).strip()
        effective_language = resolve_effective_language({})
        existing = await self._repo.get_by_scope(
            brief_kind=brief_kind,
            scope_key=bundle.scope_key,
        )
        if existing is not None and not force and _same_source_snapshot(existing.source_updated_at, bundle.source_updated_at):
            self._log_debug(
                "service.generate_brief.skip_current",
                mode="write",
                brief_kind=brief_kind.value,
                scope_key=bundle.scope_key,
                rendered_locale=effective_language,
                brief_id=int(existing.id),
            )
            return BriefGenerationResult(
                status=BriefGenerationStatus.SKIPPED,
                reason="brief_already_current",
                brief_id=int(existing.id),
                brief_kind=brief_kind,
                scope_key=bundle.scope_key,
                rendered_locale=effective_language,
                symbol=bundle.symbol,
                generated_at=existing.updated_at,
                source_updated_at=existing.source_updated_at,
            )

        prompt = await self._prompt_loader.load(f"brief.{brief_kind.value}")
        generated = await self._generator.generate(
            bundle=bundle,
            prompt=prompt,
            context=context,
            requested_provider=requested_provider,
        )
        metadata = generated.metadata
        storage_fields = _brief_storage_fields(generated, rendered_locale=metadata.effective_language)
        item = await self._repo.upsert_brief(
            existing=existing,
            payload={
                "brief_kind": brief_kind.value,
                "scope_key": bundle.scope_key,
                "symbol": bundle.symbol,
                "coin_id": bundle.coin_id,
                "content_kind": storage_fields["content_kind"],
                "content_json": storage_fields["content_json"],
                "refs_json": to_jsonable_data(bundle.refs_json),
                "context_json": to_jsonable_data(
                    {
                        "snapshot": bundle.context,
                        "ai_execution": metadata.as_dict(),
                    }
                ),
                "provider": str(metadata.actual_provider or ""),
                "model": metadata.model,
                "prompt_name": metadata.prompt_name,
                "prompt_version": int(metadata.prompt_version),
                "source_updated_at": bundle.source_updated_at,
            },
        )
        return self._result_contract(item=item)

    async def _load_context_bundle(self, *, brief_kind: BriefKind, symbol: str | None) -> BriefContextBundle:
        if brief_kind is BriefKind.MARKET:
            return await self._queries.build_market_context()
        if brief_kind is BriefKind.PORTFOLIO:
            return await self._queries.build_portfolio_context()
        if brief_kind is BriefKind.SYMBOL:
            bundle = await self._queries.build_symbol_context(str(symbol or ""))
            if bundle is None:
                raise ResourceNotFoundError(resource="symbol")
            return bundle
        raise ValidationFailedError(params={"field": "brief_kind", "value": brief_kind.value})

    def _result_contract(self, *, item: AIBrief) -> BriefGenerationResult:
        return BriefGenerationResult(
            status=BriefGenerationStatus.OK,
            brief_id=int(item.id),
            brief_kind=BriefKind(str(item.brief_kind)),
            scope_key=str(item.scope_key),
            rendered_locale=content_rendered_locale(item.content_json) or "en",
            symbol=str(item.symbol) if item.symbol is not None else None,
            generated_at=item.updated_at,
            source_updated_at=item.source_updated_at,
        )


def _same_source_snapshot(left: datetime | None, right: datetime | None) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    return left == right


__all__ = ["BriefService"]


def _brief_storage_fields(generated: BriefArtifactResult, *, rendered_locale: str) -> dict[str, object]:
    return {
        "content_kind": CONTENT_KIND_GENERATED_TEXT,
        "content_json": build_generated_text_content(
            rendered_locale=rendered_locale,
            fields={
                "title": generated.title,
                "summary": generated.summary,
                "bullets": generated.bullets,
            },
        ),
    }
