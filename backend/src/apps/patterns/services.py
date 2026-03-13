from __future__ import annotations

from src.apps.patterns.domain.lifecycle import PatternLifecycleState
from src.apps.patterns.query_services import PatternQueryService
from src.apps.patterns.read_models import PatternFeatureReadModel, PatternReadModel
from src.apps.patterns.repositories import PatternFeatureRepository, PatternRegistryRepository
from src.core.db.uow import BaseAsyncUnitOfWork


class PatternAdminService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._queries = PatternQueryService(uow.session)
        self._features = PatternFeatureRepository(uow.session)
        self._patterns = PatternRegistryRepository(uow.session)

    async def update_pattern_feature(
        self,
        feature_slug: str,
        *,
        enabled: bool,
    ) -> PatternFeatureReadModel | None:
        row = await self._features.get_for_update(feature_slug.strip())
        if row is None:
            return None
        row.enabled = enabled
        await self._uow.flush()
        item = await self._queries.get_pattern_feature_read_by_slug(str(row.feature_slug))
        return (
            item
            if item is not None
            else PatternFeatureReadModel(
                feature_slug=str(row.feature_slug),
                enabled=bool(row.enabled),
                created_at=row.created_at,
            )
        )

    async def update_pattern(
        self,
        slug: str,
        *,
        enabled: bool | None,
        lifecycle_state: str | None,
        cpu_cost: int | None,
    ) -> PatternReadModel | None:
        row = await self._patterns.get_for_update(slug.strip())
        if row is None:
            return None
        if enabled is not None:
            row.enabled = enabled
            if not enabled:
                row.lifecycle_state = PatternLifecycleState.DISABLED.value
        if lifecycle_state is not None:
            normalized_state = lifecycle_state.strip().upper()
            if normalized_state not in {item.value for item in PatternLifecycleState}:
                raise ValueError(f"Unsupported lifecycle state '{lifecycle_state}'.")
            row.lifecycle_state = normalized_state
        if cpu_cost is not None:
            row.cpu_cost = max(cpu_cost, 1)
        await self._uow.flush()
        return await self._queries.get_pattern_read_by_slug(str(row.slug))


__all__ = ["PatternAdminService"]
