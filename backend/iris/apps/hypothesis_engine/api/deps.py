from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends

from iris.apps.hypothesis_engine.api.stream_adapter import HypothesisEventStreamAdapter
from iris.apps.hypothesis_engine.query_services import HypothesisQueryService
from iris.apps.hypothesis_engine.services import PromptService, PromptSideEffectDispatcher
from iris.core.db.uow import BaseAsyncUnitOfWork, get_uow
from iris.core.http.deps import get_operation_store, get_trace_context
from iris.core.http.operation_store import (
    OperationDispatchResult,
    OperationStore,
    TaskiqJob,
    dispatch_background_operation,
)
from iris.core.http.tracing import TraceContext
from iris.core.settings import Settings, get_settings


@dataclass(slots=True, frozen=True)
class HypothesisPromptCommandGateway:
    service: PromptService
    dispatcher: PromptSideEffectDispatcher
    uow: BaseAsyncUnitOfWork


@dataclass(slots=True, frozen=True)
class HypothesisJobDispatcher:
    operation_store: OperationStore
    trace_context: TraceContext

    async def dispatch_evaluation(self) -> OperationDispatchResult:
        from iris.apps.hypothesis_engine.tasks.hypothesis_tasks import evaluate_hypotheses_job
        job = cast(TaskiqJob, evaluate_hypotheses_job)

        return await dispatch_background_operation(
            store=self.operation_store,
            operation_type="hypothesis.evaluate",
            trace_context=self.trace_context,
            deduplication_key="singleton",
            dispatch=lambda operation_id: job.kiq(operation_id=operation_id),
        )


def get_hypothesis_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> HypothesisQueryService:
    return HypothesisQueryService(uow.session)


def get_hypothesis_prompt_command_gateway(
    uow: BaseAsyncUnitOfWork = Depends(get_uow),
) -> HypothesisPromptCommandGateway:
    return HypothesisPromptCommandGateway(service=PromptService(uow), dispatcher=PromptSideEffectDispatcher(), uow=uow)


def get_hypothesis_job_dispatcher(
    operation_store: OperationStore = Depends(get_operation_store),
    trace_context: TraceContext = Depends(get_trace_context),
) -> HypothesisJobDispatcher:
    return HypothesisJobDispatcher(operation_store=operation_store, trace_context=trace_context)


def get_hypothesis_event_stream_adapter(
    settings: Settings = Depends(get_settings),
) -> HypothesisEventStreamAdapter:
    return HypothesisEventStreamAdapter(redis_url=settings.redis_url, stream_name=settings.event_stream_name)


HypothesisQueryDep = Annotated[HypothesisQueryService, Depends(get_hypothesis_query_service)]
HypothesisPromptCommandDep = Annotated[
    HypothesisPromptCommandGateway,
    Depends(get_hypothesis_prompt_command_gateway),
]
HypothesisJobDispatcherDep = Annotated[HypothesisJobDispatcher, Depends(get_hypothesis_job_dispatcher)]
HypothesisEventStreamAdapterDep = Annotated[
    HypothesisEventStreamAdapter,
    Depends(get_hypothesis_event_stream_adapter),
]


__all__ = [
    "HypothesisEventStreamAdapterDep",
    "HypothesisJobDispatcher",
    "HypothesisJobDispatcherDep",
    "HypothesisPromptCommandDep",
    "HypothesisPromptCommandGateway",
    "HypothesisQueryDep",
]
