from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.patterns.models import PatternFeature, PatternRegistry
from src.core.db.persistence import AsyncRepository


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


__all__ = ["PatternFeatureRepository", "PatternRegistryRepository"]
