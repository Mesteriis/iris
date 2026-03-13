from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from src.apps.market_data.query_services import MarketDataQueryService
from src.apps.market_data.services import MarketDataService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow
from src.core.http.deps import get_operation_store, get_trace_context
from src.core.http.operation_store import OperationStore, dispatch_background_operation
from src.core.http.operations import OperationStatusResponse
from src.core.http.tracing import TraceContext


@dataclass(slots=True, frozen=True)
class MarketDataBackfillTrigger:
    event: object | None

    def schedule_after_commit(self, uow: BaseAsyncUnitOfWork) -> None:
        trigger = getattr(self.event, "set", None)
        if callable(trigger):
            uow.add_after_commit_action(trigger)


@dataclass(slots=True, frozen=True)
class MarketDataCommandGateway:
    service: MarketDataService
    uow: BaseAsyncUnitOfWork
    backfill_trigger: MarketDataBackfillTrigger


@dataclass(slots=True, frozen=True)
class MarketDataJobDispatcher:
    operation_store: OperationStore
    trace_context: TraceContext

    async def dispatch_coin_history(self, *, symbol: str, mode: str, force: bool) -> OperationStatusResponse:
        from src.apps.market_data.tasks import run_coin_history_job

        return await dispatch_background_operation(
            store=self.operation_store,
            operation_type="market_data.coin_history.sync",
            trace_context=self.trace_context,
            dispatch=lambda operation_id: run_coin_history_job.kiq(
                symbol=symbol,
                mode=mode,
                force=force,
                operation_id=operation_id,
            ),
        )


def get_market_data_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> MarketDataQueryService:
    return MarketDataQueryService(uow.session)


def get_market_data_backfill_trigger(request: Request) -> MarketDataBackfillTrigger:
    return MarketDataBackfillTrigger(event=getattr(request.app.state, "taskiq_backfill_event", None))


def get_market_data_command_gateway(
    uow: BaseAsyncUnitOfWork = Depends(get_uow),
    backfill_trigger: MarketDataBackfillTrigger = Depends(get_market_data_backfill_trigger),
) -> MarketDataCommandGateway:
    return MarketDataCommandGateway(service=MarketDataService(uow), uow=uow, backfill_trigger=backfill_trigger)


def get_market_data_job_dispatcher(
    operation_store: OperationStore = Depends(get_operation_store),
    trace_context: TraceContext = Depends(get_trace_context),
) -> MarketDataJobDispatcher:
    return MarketDataJobDispatcher(operation_store=operation_store, trace_context=trace_context)


MarketDataQueryDep = Annotated[MarketDataQueryService, Depends(get_market_data_query_service)]
MarketDataCommandDep = Annotated[MarketDataCommandGateway, Depends(get_market_data_command_gateway)]
MarketDataJobDispatcherDep = Annotated[MarketDataJobDispatcher, Depends(get_market_data_job_dispatcher)]


__all__ = [
    "MarketDataBackfillTrigger",
    "MarketDataCommandDep",
    "MarketDataCommandGateway",
    "MarketDataJobDispatcher",
    "MarketDataJobDispatcherDep",
    "MarketDataQueryDep",
]
