from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from src.apps.hypothesis_engine.api.stream_adapter import HypothesisEventStreamAdapter
from src.apps.hypothesis_engine.query_services import HypothesisQueryService
from src.apps.hypothesis_engine.services import PromptService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow
from src.core.settings import Settings, get_settings


@dataclass(slots=True, frozen=True)
class HypothesisPromptCommandGateway:
    service: PromptService
    uow: BaseAsyncUnitOfWork


class HypothesisJobDispatcher:
    async def dispatch_evaluation(self) -> None:
        from src.apps.hypothesis_engine.tasks.hypothesis_tasks import evaluate_hypotheses_job

        await evaluate_hypotheses_job.kiq()


def get_hypothesis_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> HypothesisQueryService:
    return HypothesisQueryService(uow.session)


def get_hypothesis_prompt_command_gateway(
    uow: BaseAsyncUnitOfWork = Depends(get_uow),
) -> HypothesisPromptCommandGateway:
    return HypothesisPromptCommandGateway(service=PromptService(uow), uow=uow)


def get_hypothesis_job_dispatcher() -> HypothesisJobDispatcher:
    return HypothesisJobDispatcher()


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
