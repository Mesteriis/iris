from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.indicators.query_services import IndicatorQueryService
from src.apps.indicators.read_models import (
    MarketRadarCoinReadModel,
    MarketRadarReadModel,
    MarketRegimeChangeReadModel,
    market_radar_coin_read_model_from_mapping,
)


class MarketRadarQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._queries = IndicatorQueryService(session)

    @staticmethod
    def metric_rows(rows: Sequence[Mapping[str, object]]) -> tuple[MarketRadarCoinReadModel, ...]:
        return tuple(market_radar_coin_read_model_from_mapping(row) for row in rows)

    async def list_recent_regime_changes(self, *, limit: int) -> tuple[MarketRegimeChangeReadModel, ...]:
        return await self._queries.list_recent_regime_changes(limit=limit)

    async def get_market_radar(self, *, limit: int = 8) -> MarketRadarReadModel:
        return await self._queries.get_market_radar(limit=limit)


__all__ = ["MarketRadarQueryService"]
