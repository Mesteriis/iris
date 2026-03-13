from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from src.apps.news.query_services import NewsQueryService
from src.apps.news.services import NewsService, TelegramSessionOnboardingService, TelegramSourceProvisioningService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow
from src.core.http.deps import get_operation_store, get_trace_context
from src.core.http.operation_store import OperationStore, dispatch_background_operation
from src.core.http.operations import OperationStatusResponse
from src.core.http.tracing import TraceContext


@dataclass(slots=True, frozen=True)
class NewsCommandGateway:
    service: NewsService
    uow: BaseAsyncUnitOfWork


@dataclass(slots=True, frozen=True)
class TelegramProvisioningGateway:
    service: TelegramSourceProvisioningService
    uow: BaseAsyncUnitOfWork


@dataclass(slots=True, frozen=True)
class NewsJobDispatcher:
    operation_store: OperationStore
    trace_context: TraceContext

    async def dispatch_source_poll(self, *, source_id: int, limit: int) -> OperationStatusResponse:
        from src.apps.news.tasks import poll_news_source_job

        return await dispatch_background_operation(
            store=self.operation_store,
            operation_type="news.source.poll",
            trace_context=self.trace_context,
            dispatch=lambda operation_id: poll_news_source_job.kiq(
                source_id=source_id,
                limit=limit,
                operation_id=operation_id,
            ),
        )


def get_news_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> NewsQueryService:
    return NewsQueryService(uow.session)


def get_news_command_gateway(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> NewsCommandGateway:
    return NewsCommandGateway(service=NewsService(uow), uow=uow)


def get_telegram_provisioning_gateway(
    uow: BaseAsyncUnitOfWork = Depends(get_uow),
) -> TelegramProvisioningGateway:
    return TelegramProvisioningGateway(service=TelegramSourceProvisioningService(uow), uow=uow)


def get_telegram_session_onboarding_service() -> TelegramSessionOnboardingService:
    return TelegramSessionOnboardingService()


def get_news_job_dispatcher(
    operation_store: OperationStore = Depends(get_operation_store),
    trace_context: TraceContext = Depends(get_trace_context),
) -> NewsJobDispatcher:
    return NewsJobDispatcher(operation_store=operation_store, trace_context=trace_context)


NewsQueryDep = Annotated[NewsQueryService, Depends(get_news_query_service)]
NewsCommandDep = Annotated[NewsCommandGateway, Depends(get_news_command_gateway)]
TelegramProvisioningDep = Annotated[TelegramProvisioningGateway, Depends(get_telegram_provisioning_gateway)]
TelegramSessionOnboardingDep = Annotated[
    TelegramSessionOnboardingService,
    Depends(get_telegram_session_onboarding_service),
]
NewsJobDispatcherDep = Annotated[NewsJobDispatcher, Depends(get_news_job_dispatcher)]


__all__ = [
    "NewsCommandDep",
    "NewsCommandGateway",
    "NewsJobDispatcher",
    "NewsJobDispatcherDep",
    "NewsQueryDep",
    "TelegramProvisioningDep",
    "TelegramProvisioningGateway",
    "TelegramSessionOnboardingDep",
]
