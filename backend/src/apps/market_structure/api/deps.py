from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Query

from src.apps.market_structure.query_services import MarketStructureQueryService
from src.apps.market_structure.services import MarketStructureService, MarketStructureSourceProvisioningService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow
from src.core.http.deps import get_operation_store, get_trace_context
from src.core.http.operation_store import OperationStore, dispatch_background_operation
from src.core.http.operations import OperationStatusResponse
from src.core.http.tracing import TraceContext


@dataclass(slots=True, frozen=True)
class MarketStructureCommandGateway:
    service: MarketStructureService
    uow: BaseAsyncUnitOfWork


@dataclass(slots=True, frozen=True)
class MarketStructureProvisioningGateway:
    service: MarketStructureSourceProvisioningService
    uow: BaseAsyncUnitOfWork


@dataclass(slots=True, frozen=True)
class MarketStructureIngestAccess:
    token: str | None


@dataclass(slots=True, frozen=True)
class MarketStructureJobDispatcher:
    operation_store: OperationStore
    trace_context: TraceContext

    async def dispatch_source_poll(self, *, source_id: int, limit: int) -> OperationStatusResponse:
        from src.apps.market_structure.tasks import poll_market_structure_source_job

        return await dispatch_background_operation(
            store=self.operation_store,
            operation_type="market_structure.source.poll",
            trace_context=self.trace_context,
            dispatch=lambda operation_id: poll_market_structure_source_job.kiq(
                source_id=source_id,
                limit=limit,
                operation_id=operation_id,
            ),
        )

    async def dispatch_health_refresh(self) -> OperationStatusResponse:
        from src.apps.market_structure.tasks import refresh_market_structure_source_health_job

        return await dispatch_background_operation(
            store=self.operation_store,
            operation_type="market_structure.health.refresh",
            trace_context=self.trace_context,
            dispatch=lambda operation_id: refresh_market_structure_source_health_job.kiq(operation_id=operation_id),
        )


def get_market_structure_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> MarketStructureQueryService:
    return MarketStructureQueryService(uow.session)


def get_market_structure_command_gateway(
    uow: BaseAsyncUnitOfWork = Depends(get_uow),
) -> MarketStructureCommandGateway:
    return MarketStructureCommandGateway(service=MarketStructureService(uow), uow=uow)


def get_market_structure_provisioning_gateway(
    uow: BaseAsyncUnitOfWork = Depends(get_uow),
) -> MarketStructureProvisioningGateway:
    return MarketStructureProvisioningGateway(service=MarketStructureSourceProvisioningService(uow), uow=uow)


async def resolve_market_structure_ingest_access(
    token: str | None = Query(default=None),
    x_iris_ingest_token: str | None = Header(default=None, alias="X-IRIS-Ingest-Token"),
) -> MarketStructureIngestAccess:
    return MarketStructureIngestAccess(token=x_iris_ingest_token or token)


def get_market_structure_job_dispatcher(
    operation_store: OperationStore = Depends(get_operation_store),
    trace_context: TraceContext = Depends(get_trace_context),
) -> MarketStructureJobDispatcher:
    return MarketStructureJobDispatcher(operation_store=operation_store, trace_context=trace_context)


MarketStructureQueryDep = Annotated[MarketStructureQueryService, Depends(get_market_structure_query_service)]
MarketStructureCommandDep = Annotated[MarketStructureCommandGateway, Depends(get_market_structure_command_gateway)]
MarketStructureProvisioningDep = Annotated[
    MarketStructureProvisioningGateway,
    Depends(get_market_structure_provisioning_gateway),
]
MarketStructureIngestAccessDep = Annotated[
    MarketStructureIngestAccess,
    Depends(resolve_market_structure_ingest_access),
]
MarketStructureJobDispatcherDep = Annotated[
    MarketStructureJobDispatcher,
    Depends(get_market_structure_job_dispatcher),
]


__all__ = [
    "MarketStructureCommandDep",
    "MarketStructureCommandGateway",
    "MarketStructureIngestAccess",
    "MarketStructureIngestAccessDep",
    "MarketStructureJobDispatcher",
    "MarketStructureJobDispatcherDep",
    "MarketStructureProvisioningDep",
    "MarketStructureProvisioningGateway",
    "MarketStructureQueryDep",
]
