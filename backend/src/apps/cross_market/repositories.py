from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.cross_market.models import CoinRelation, SectorMetric
from src.core.db.persistence import AsyncRepository


class CoinRelationRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="cross_market", repository_name="CoinRelationRepository")

    async def upsert_many(self, rows: Sequence[dict[str, object]]) -> int:
        self._log_info("repo.upsert_cross_market_relations", mode="write", bulk=True, count=len(rows))
        if not rows:
            return 0
        stmt = insert(CoinRelation).values(list(rows))
        stmt = stmt.on_conflict_do_update(
            index_elements=["leader_coin_id", "follower_coin_id"],
            set_={
                "correlation": stmt.excluded.correlation,
                "lag_hours": stmt.excluded.lag_hours,
                "confidence": stmt.excluded.confidence,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return len(rows)


class SectorMetricRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="cross_market", repository_name="SectorMetricRepository")

    async def upsert_many(self, rows: Sequence[dict[str, object]]) -> int:
        self._log_info("repo.upsert_cross_market_sector_metrics", mode="write", bulk=True, count=len(rows))
        if not rows:
            return 0
        stmt = insert(SectorMetric).values(list(rows))
        stmt = stmt.on_conflict_do_update(
            index_elements=["sector_id", "timeframe"],
            set_={
                "sector_strength": stmt.excluded.sector_strength,
                "relative_strength": stmt.excluded.relative_strength,
                "capital_flow": stmt.excluded.capital_flow,
                "avg_price_change_24h": stmt.excluded.avg_price_change_24h,
                "avg_volume_change_24h": stmt.excluded.avg_volume_change_24h,
                "volatility": stmt.excluded.volatility,
                "trend": stmt.excluded.trend,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return len(rows)


__all__ = ["CoinRelationRepository", "SectorMetricRepository"]
