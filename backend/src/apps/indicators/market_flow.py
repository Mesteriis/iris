from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.indicators.query_services import IndicatorQueryService
from src.apps.indicators.read_models import MarketFlowReadModel, MarketLeaderReadModel, SectorRotationReadModel


class MarketFlowQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._queries = IndicatorQueryService(session)

    async def list_recent_market_leaders(self, *, limit: int) -> tuple[MarketLeaderReadModel, ...]:
        return await self._queries.list_recent_market_leaders(limit=limit)

    async def list_recent_sector_rotations(self, *, limit: int) -> tuple[SectorRotationReadModel, ...]:
        return await self._queries.list_recent_sector_rotations(limit=limit)

    async def get_market_flow(self, *, limit: int = 8, timeframe: int = 60) -> MarketFlowReadModel:
        return await self._queries.get_market_flow(limit=limit, timeframe=timeframe)


__all__ = ["MarketFlowQueryService"]
