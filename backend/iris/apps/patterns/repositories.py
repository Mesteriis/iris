from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from iris.apps.patterns.models import MarketCycle, PatternFeature, PatternRegistry
from iris.apps.signals.models import Signal
from iris.core.db.persistence import AsyncRepository


class PatternFeatureRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="patterns", repository_name="PatternFeatureRepository")

    async def get_for_update(self, feature_slug: str) -> PatternFeature | None:
        self._log_debug("repo.get_pattern_feature_for_update", mode="write", feature_slug=feature_slug, lock=True)
        row = await self.session.scalar(
            select(PatternFeature).where(PatternFeature.feature_slug == feature_slug).with_for_update().limit(1)
        )
        self._log_debug("repo.get_pattern_feature_for_update.result", mode="write", found=row is not None)
        return row

    async def refresh(self, feature: PatternFeature) -> None:
        await self.session.refresh(feature)


class PatternRegistryRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="patterns", repository_name="PatternRegistryRepository")

    async def get_for_update(self, slug: str) -> PatternRegistry | None:
        self._log_debug("repo.get_pattern_registry_for_update", mode="write", slug=slug, lock=True)
        row = await self.session.scalar(
            select(PatternRegistry).where(PatternRegistry.slug == slug).with_for_update().limit(1)
        )
        self._log_debug("repo.get_pattern_registry_for_update.result", mode="write", found=row is not None)
        return row

    async def refresh(self, pattern: PatternRegistry) -> None:
        await self.session.refresh(pattern)


class PatternSignalRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="patterns", repository_name="PatternSignalRepository")

    async def insert_new(self, *, rows: list[dict[str, object]]) -> int:
        self._log_debug("repo.insert_pattern_signals", mode="write", bulk=True, count=len(rows))
        if not rows:
            return 0
        insert_stmt = insert(Signal).values(rows)
        stmt = insert_stmt.on_conflict_do_nothing(
            index_elements=["coin_id", "timeframe", "candle_timestamp", "signal_type"],
        ).returning(Signal.id)
        result = await self.session.execute(stmt)
        return len(result.all())


class PatternMarketCycleRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="patterns", repository_name="PatternMarketCycleRepository")

    async def get(self, *, coin_id: int, timeframe: int) -> MarketCycle | None:
        self._log_debug(
            "repo.get_pattern_market_cycle",
            mode="read",
            coin_id=int(coin_id),
            timeframe=int(timeframe),
        )
        row = await self.session.get(MarketCycle, (int(coin_id), int(timeframe)))
        self._log_debug("repo.get_pattern_market_cycle.result", mode="read", found=row is not None)
        return row

    async def upsert(
        self,
        *,
        coin_id: int,
        timeframe: int,
        cycle_phase: str,
        confidence: float,
        detected_at: datetime,
    ) -> None:
        self._log_debug(
            "repo.upsert_pattern_market_cycle",
            mode="write",
            coin_id=int(coin_id),
            timeframe=int(timeframe),
        )
        stmt = insert(MarketCycle).values(
            {
                "coin_id": int(coin_id),
                "timeframe": int(timeframe),
                "cycle_phase": str(cycle_phase),
                "confidence": float(confidence),
                "detected_at": detected_at,
            }
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["coin_id", "timeframe"],
            set_={
                "cycle_phase": stmt.excluded.cycle_phase,
                "confidence": stmt.excluded.confidence,
                "detected_at": stmt.excluded.detected_at,
            },
        )
        await self.session.execute(stmt)


__all__ = [
    "PatternFeatureRepository",
    "PatternMarketCycleRepository",
    "PatternRegistryRepository",
    "PatternSignalRepository",
]
