from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import importlib.util

import pytest

from src.apps.patterns.models import PatternFeature, PatternRegistry, PatternStatistic
from src.apps.patterns.query_services import PatternQueryService
from src.apps.patterns.services import PatternAdminService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork
from tests.patterns_support import seed_pattern_api_state


async def _seed_pattern_metadata(async_db_session) -> None:
    if await async_db_session.get(PatternFeature, "pattern_context_engine") is None:
        async_db_session.add(PatternFeature(feature_slug="pattern_context_engine", enabled=True))
    if await async_db_session.get(PatternRegistry, "bull_flag") is None:
        async_db_session.add(
            PatternRegistry(
                slug="bull_flag",
                category="continuation",
                enabled=True,
                cpu_cost=2,
                lifecycle_state="ACTIVE",
            )
        )
    if await async_db_session.get(PatternStatistic, ("bull_flag", 15, "all")) is None:
        async_db_session.add(
            PatternStatistic(
                pattern_slug="bull_flag",
                timeframe=15,
                market_regime="all",
                sample_size=12,
                total_signals=12,
                successful_signals=8,
                success_rate=0.6667,
                avg_return=0.14,
                avg_drawdown=-0.05,
                temperature=0.32,
                enabled=True,
                last_evaluated_at=datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 3, 12, 10, 5, tzinfo=timezone.utc),
            )
        )
    await async_db_session.commit()


@pytest.mark.asyncio
async def test_patterns_query_returns_immutable_read_models(async_db_session, db_session) -> None:
    seed_pattern_api_state(db_session)
    await _seed_pattern_metadata(async_db_session)
    items = await PatternQueryService(async_db_session).list_patterns()

    assert items
    with pytest.raises(FrozenInstanceError):
        items[0].slug = "changed"
    if items[0].statistics:
        with pytest.raises(FrozenInstanceError):
            items[0].statistics[0].temperature = 0.0

    signals = await PatternQueryService(async_db_session).list_coin_patterns("BTCUSD_EVT", limit=10)
    assert signals
    with pytest.raises(FrozenInstanceError):
        signals[0].signal_type = "changed"
    assert isinstance(signals[0].cluster_membership, tuple)


@pytest.mark.asyncio
async def test_patterns_persistence_logs_cover_query_repo_and_uow(async_db_session, monkeypatch) -> None:
    await _seed_pattern_metadata(async_db_session)
    events: list[str] = []

    def _debug(message: str, *args, **kwargs) -> None:
        del args, kwargs
        events.append(message)

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    monkeypatch.setattr(PERSISTENCE_LOGGER, "debug", _debug)
    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)

    async with SessionUnitOfWork(async_db_session) as uow:
        updated = await PatternAdminService(uow).update_pattern_feature("pattern_context_engine", enabled=False)
        items = await PatternQueryService(uow.session).list_patterns()

    assert updated is not None
    assert items
    assert "uow.begin" in events
    assert "repo.get_pattern_feature_for_update" in events
    assert "query.list_patterns" in events
    assert "uow.commit" in events


def test_patterns_legacy_selector_module_is_absent() -> None:
    assert importlib.util.find_spec("src.apps.patterns.selectors") is None


def test_patterns_legacy_engine_module_is_absent() -> None:
    assert importlib.util.find_spec("src.apps.patterns.domain.engine") is None


def test_patterns_legacy_cluster_and_hierarchy_modules_are_absent() -> None:
    assert importlib.util.find_spec("src.apps.patterns.domain.clusters") is None
    assert importlib.util.find_spec("src.apps.patterns.domain.hierarchy") is None
