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


def _metric_rows(rows: Sequence[Mapping[str, object]]) -> tuple[MarketRadarCoinReadModel, ...]:
    return tuple(market_radar_coin_read_model_from_mapping(row) for row in rows)


async def _recent_regime_changes(db: AsyncSession, *, limit: int) -> tuple[MarketRegimeChangeReadModel, ...]:
    return await IndicatorQueryService(db).list_recent_regime_changes(limit=limit)


async def get_market_radar(db: AsyncSession, *, limit: int = 8) -> MarketRadarReadModel:
    return await IndicatorQueryService(db).get_market_radar(limit=limit)


__all__ = ["_metric_rows", "_recent_regime_changes", "get_market_radar"]
