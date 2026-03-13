from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from src.apps.market_data.query_services import MarketDataQueryService
from src.apps.market_data.services import MarketDataService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow


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


class MarketDataJobDispatcher:
    async def dispatch_coin_history(self, *, symbol: str, mode: str, force: bool) -> None:
        from src.apps.market_data.tasks import run_coin_history_job

        await run_coin_history_job.kiq(symbol=symbol, mode=mode, force=force)


def get_market_data_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> MarketDataQueryService:
    return MarketDataQueryService(uow.session)


def get_market_data_backfill_trigger(request: Request) -> MarketDataBackfillTrigger:
    return MarketDataBackfillTrigger(event=getattr(request.app.state, "taskiq_backfill_event", None))


def get_market_data_command_gateway(
    uow: BaseAsyncUnitOfWork = Depends(get_uow),
    backfill_trigger: MarketDataBackfillTrigger = Depends(get_market_data_backfill_trigger),
) -> MarketDataCommandGateway:
    return MarketDataCommandGateway(service=MarketDataService(uow), uow=uow, backfill_trigger=backfill_trigger)


def get_market_data_job_dispatcher() -> MarketDataJobDispatcher:
    return MarketDataJobDispatcher()


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
