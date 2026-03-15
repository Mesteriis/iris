from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder

from src.apps.briefs.contracts import BriefGenerationResult, BriefGenerationStatus, BriefKind
from src.apps.briefs.language import resolve_effective_language
from src.apps.briefs.models import AIBrief
from src.apps.briefs.query_services import BriefQueryService
from src.apps.briefs.read_models import BriefContextBundle
from src.apps.briefs.repositories import BriefRepository
from src.apps.briefs.services.generation_service import BriefGenerationService
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork


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
        self._generator = BriefGenerationService()

    async def generate_and_store(
        self,
        *,
        brief_kind: BriefKind,
        language: str | None = None,
        symbol: str | None = None,
        requested_provider: str | None = None,
        force: bool = False,
    ) -> BriefGenerationResult:
        bundle = await self._load_context_bundle(brief_kind=brief_kind, symbol=symbol)
        context = dict(bundle.context)
        if language is not None and str(language).strip():
            context["language"] = str(language).strip()
        if requested_provider is not None and str(requested_provider).strip():
            context["requested_provider"] = str(requested_provider).strip()
        effective_language = resolve_effective_language(context)
        existing = await self._repo.get_by_scope(
            brief_kind=brief_kind,
            scope_key=bundle.scope_key,
            language=effective_language,
        )
        if existing is not None and not force and _same_source_snapshot(existing.source_updated_at, bundle.source_updated_at):
            self._log_debug(
                "service.generate_brief.skip_current",
                mode="write",
                brief_kind=brief_kind.value,
                scope_key=bundle.scope_key,
                language=effective_language,
                brief_id=int(existing.id),
            )
            return BriefGenerationResult(
                status=BriefGenerationStatus.SKIPPED,
                reason="brief_already_current",
                brief_id=int(existing.id),
                brief_kind=brief_kind,
                scope_key=bundle.scope_key,
                language=effective_language,
                symbol=bundle.symbol,
                generated_at=existing.updated_at,
                source_updated_at=existing.source_updated_at,
            )

        generated = await self._generator.generate(
            bundle=bundle,
            context=context,
            requested_provider=requested_provider,
        )
        item = await self._repo.upsert_brief(
            existing=existing,
            payload={
                "brief_kind": brief_kind.value,
                "scope_key": bundle.scope_key,
                "symbol": bundle.symbol,
                "coin_id": bundle.coin_id,
                "language": str(generated["effective_language"]),
                "title": str(generated["title"]),
                "summary": str(generated["summary"]),
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
                raise LookupError(f"Symbol scope '{str(symbol or '').strip().upper()}' is not available.")
            return bundle
        raise ValueError(f"Unsupported brief kind '{brief_kind.value}'.")

    def _result_contract(self, *, item: AIBrief) -> BriefGenerationResult:
        return BriefGenerationResult(
            status=BriefGenerationStatus.OK,
            brief_id=int(item.id),
            brief_kind=BriefKind(str(item.brief_kind)),
            scope_key=str(item.scope_key),
            language=str(item.language),
            symbol=str(item.symbol) if item.symbol is not None else None,
            generated_at=item.updated_at,
            source_updated_at=item.source_updated_at,
        )


def _same_source_snapshot(left, right) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    return left == right


__all__ = ["BriefService"]
