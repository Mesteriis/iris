from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.anomalies.models import MarketAnomaly
from app.apps.portfolio.models import PortfolioPosition


def _serialize_anomaly(anomaly: MarketAnomaly) -> dict[str, object]:
    return {
        "id": int(anomaly.id),
        "coin_id": int(anomaly.coin_id),
        "symbol": anomaly.symbol,
        "timeframe": int(anomaly.timeframe),
        "anomaly_type": anomaly.anomaly_type,
        "severity": anomaly.severity,
        "confidence": float(anomaly.confidence),
        "score": float(anomaly.score),
        "status": anomaly.status,
        "detected_at": anomaly.detected_at,
        "window_start": anomaly.window_start,
        "window_end": anomaly.window_end,
        "market_regime": anomaly.market_regime,
        "sector": anomaly.sector,
        "summary": anomaly.summary,
        "payload_json": anomaly.payload_json,
    }


async def list_active_anomalies_async(
    db: AsyncSession,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    stmt = (
        select(MarketAnomaly)
        .where(MarketAnomaly.status.in_(("new", "active")))
        .order_by(MarketAnomaly.detected_at.desc())
        .limit(limit)
    )
    if symbol is not None:
        stmt = stmt.where(MarketAnomaly.symbol == symbol.upper())
    if timeframe is not None:
        stmt = stmt.where(MarketAnomaly.timeframe == timeframe)
    items = (await db.execute(stmt)).scalars().all()
    return [_serialize_anomaly(item) for item in items]


async def list_portfolio_relevant_anomalies_async(
    db: AsyncSession,
    *,
    limit: int = 25,
) -> list[dict[str, object]]:
    items = (
        await db.execute(
            select(MarketAnomaly)
            .join(
                PortfolioPosition,
                (PortfolioPosition.coin_id == MarketAnomaly.coin_id)
                & (PortfolioPosition.timeframe == MarketAnomaly.timeframe),
            )
            .where(
                MarketAnomaly.status.in_(("new", "active")),
                PortfolioPosition.status == "open",
            )
            .order_by(MarketAnomaly.detected_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [_serialize_anomaly(item) for item in items]
