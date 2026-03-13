from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from src.apps.indicators.query_services import IndicatorQueryService
from src.apps.patterns.query_services import PatternQueryService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow


@dataclass(slots=True, frozen=True)
class IndicatorReadFacade:
    indicators: IndicatorQueryService
    patterns: PatternQueryService

    async def list_coin_metrics(self):
        return await self.indicators.list_coin_metrics()

    async def list_market_cycles(self, *, symbol: str | None, timeframe: int | None):
        return await self.patterns.list_market_cycles(symbol=symbol, timeframe=timeframe)

    async def get_market_radar(self, *, limit: int):
        return await self.indicators.get_market_radar(limit=limit)

    async def get_market_flow(self, *, limit: int, timeframe: int):
        return await self.indicators.get_market_flow(limit=limit, timeframe=timeframe)


def get_indicator_read_facade(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> IndicatorReadFacade:
    return IndicatorReadFacade(
        indicators=IndicatorQueryService(uow.session),
        patterns=PatternQueryService(uow.session),
    )


IndicatorReadDep = Annotated[IndicatorReadFacade, Depends(get_indicator_read_facade)]

__all__ = ["IndicatorReadDep", "IndicatorReadFacade"]
