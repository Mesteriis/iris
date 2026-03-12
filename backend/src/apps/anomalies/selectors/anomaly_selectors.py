from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.anomalies.query_services import AnomalyQueryService
from src.apps.anomalies.read_models import anomaly_read_model_to_legacy_dict


async def list_active_anomalies_async(
    db: AsyncSession,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    items = await AnomalyQueryService(db).list_active_anomalies(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )
    return [anomaly_read_model_to_legacy_dict(item) for item in items]


async def list_portfolio_relevant_anomalies_async(
    db: AsyncSession,
    *,
    limit: int = 25,
) -> list[dict[str, object]]:
    items = await AnomalyQueryService(db).list_portfolio_relevant_anomalies(limit=limit)
    return [anomaly_read_model_to_legacy_dict(item) for item in items]
