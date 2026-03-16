from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends

from src.apps.explanations.contracts import ExplainKind
from src.apps.explanations.language import resolve_effective_language
from src.apps.explanations.query_services import ExplanationQueryService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow
from src.core.http.deps import get_operation_store, get_trace_context
from src.core.http.operation_store import (
    OperationDispatchResult,
    OperationStore,
    TaskiqJob,
    dispatch_background_operation,
)
from src.core.http.tracing import TraceContext


@dataclass(slots=True, frozen=True)
class ExplanationJobDispatcher:
    operation_store: OperationStore
    trace_context: TraceContext

    async def dispatch_generation(
        self,
        *,
        explain_kind: ExplainKind,
        subject_id: int,
        requested_provider: str | None = None,
        force: bool = False,
    ) -> OperationDispatchResult:
        from src.apps.explanations.tasks import generate_explanation_job
        job = cast(TaskiqJob, generate_explanation_job)

        effective_language = resolve_effective_language({})
        return await dispatch_background_operation(
            store=self.operation_store,
            operation_type="explain.generate",
            trace_context=self.trace_context,
            deduplication_key=f"kind:{explain_kind.value}:subject:{int(subject_id)}",
            dispatch=lambda operation_id: job.kiq(
                explain_kind=explain_kind.value,
                subject_id=int(subject_id),
                requested_provider=requested_provider,
                force=force,
                operation_id=operation_id,
            ),
        )


_UOW_DEP = Depends(get_uow)
_OPERATION_STORE_DEP = Depends(get_operation_store)
_TRACE_CONTEXT_DEP = Depends(get_trace_context)


def get_explanation_query_service(uow: BaseAsyncUnitOfWork = _UOW_DEP) -> ExplanationQueryService:
    return ExplanationQueryService(uow.session)


def get_explanation_job_dispatcher(
    operation_store: OperationStore = _OPERATION_STORE_DEP,
    trace_context: TraceContext = _TRACE_CONTEXT_DEP,
) -> ExplanationJobDispatcher:
    return ExplanationJobDispatcher(operation_store=operation_store, trace_context=trace_context)


ExplanationQueryDep = Annotated[ExplanationQueryService, Depends(get_explanation_query_service)]
ExplanationJobDispatcherDep = Annotated[ExplanationJobDispatcher, Depends(get_explanation_job_dispatcher)]

__all__ = ["ExplanationJobDispatcher", "ExplanationJobDispatcherDep", "ExplanationQueryDep"]
