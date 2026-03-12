from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.indicators.query_services import IndicatorQueryService
from src.apps.indicators.read_models import MarketFlowReadModel, MarketLeaderReadModel, SectorRotationReadModel


async def _recent_market_leaders(db: AsyncSession, *, limit: int) -> tuple[MarketLeaderReadModel, ...]:
    return await IndicatorQueryService(db).list_recent_market_leaders(limit=limit)


async def _recent_sector_rotations(db: AsyncSession, *, limit: int) -> tuple[SectorRotationReadModel, ...]:
    return await IndicatorQueryService(db).list_recent_sector_rotations(limit=limit)


async def get_market_flow(db: AsyncSession, *, limit: int = 8, timeframe: int = 60) -> MarketFlowReadModel:
    return await IndicatorQueryService(db).get_market_flow(limit=limit, timeframe=timeframe)


__all__ = ["_recent_market_leaders", "_recent_sector_rotations", "get_market_flow"]
