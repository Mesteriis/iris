from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from src.apps.briefs.contracts import BriefKind, build_scope_key
from src.apps.briefs.language import resolve_effective_language
from src.apps.briefs.query_services import BriefQueryService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow
from src.core.http.deps import get_operation_store, get_trace_context
from src.core.http.operation_store import OperationDispatchResult, OperationStore, dispatch_background_operation
from src.core.http.tracing import TraceContext


@dataclass(slots=True, frozen=True)
class BriefJobDispatcher:
    operation_store: OperationStore
    trace_context: TraceContext

    async def dispatch_generation(
        self,
        *,
        brief_kind: BriefKind,
        symbol: str | None = None,
        force: bool = False,
        requested_provider: str | None = None,
    ) -> OperationDispatchResult:
        from src.apps.briefs.tasks import generate_brief_job

        normalized_symbol = str(symbol).strip().upper() if symbol is not None and str(symbol).strip() else None
        effective_language = resolve_effective_language({})
        scope_key = build_scope_key(brief_kind, symbol=normalized_symbol)
        return await dispatch_background_operation(
            store=self.operation_store,
            operation_type="brief.generate",
            trace_context=self.trace_context,
            deduplication_key=f"kind:{brief_kind.value}:scope:{scope_key}",
            dispatch=lambda operation_id: generate_brief_job.kiq(
                brief_kind=brief_kind.value,
                symbol=normalized_symbol,
                force=force,
                requested_provider=requested_provider,
                operation_id=operation_id,
            ),
        )


_UOW_DEP = Depends(get_uow)
_OPERATION_STORE_DEP = Depends(get_operation_store)
_TRACE_CONTEXT_DEP = Depends(get_trace_context)


def get_brief_query_service(uow: BaseAsyncUnitOfWork = _UOW_DEP) -> BriefQueryService:
    return BriefQueryService(uow.session)


def get_brief_job_dispatcher(
    operation_store: OperationStore = _OPERATION_STORE_DEP,
    trace_context: TraceContext = _TRACE_CONTEXT_DEP,
) -> BriefJobDispatcher:
    return BriefJobDispatcher(operation_store=operation_store, trace_context=trace_context)


BriefQueryDep = Annotated[BriefQueryService, Depends(get_brief_query_service)]
BriefJobDispatcherDep = Annotated[BriefJobDispatcher, Depends(get_brief_job_dispatcher)]

__all__ = ["BriefJobDispatcher", "BriefJobDispatcherDep", "BriefQueryDep"]
