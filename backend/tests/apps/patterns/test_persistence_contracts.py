from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.apps.patterns.models import PatternFeature, PatternRegistry, PatternStatistic
from src.apps.patterns.query_services import PatternQueryService
from src.apps.patterns.selectors import (
    get_coin_regimes,
    get_pattern,
    list_coin_patterns,
    list_market_cycles,
    list_pattern_features,
    list_patterns,
    list_sector_metrics,
    list_sectors,
    update_pattern,
    update_pattern_feature,
)
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


def test_patterns_legacy_compatibility_queries_emit_deprecation_logs(db_session, monkeypatch) -> None:
    seed_pattern_api_state(db_session)
    events: list[str] = []

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)
    monkeypatch.setattr(
        "src.apps.patterns.selectors.build_sector_narratives",
        lambda _db: [
            SimpleNamespace(
                timeframe=60,
                top_sector="store_of_value",
                rotation_state="sector_leadership_change",
                btc_dominance=None,
                capital_wave="large_caps",
            )
        ],
    )

    patterns = list_patterns(db_session)
    pattern = get_pattern(db_session, "bull_flag")
    features = list_pattern_features(db_session)
    coin_patterns = list_coin_patterns(db_session, "BTCUSD_EVT", limit=5)
    regimes = get_coin_regimes(db_session, "BTCUSD_EVT")
    sectors = list_sectors(db_session)
    sector_metrics = list_sector_metrics(db_session, timeframe=60)
    cycles = list_market_cycles(db_session, symbol="BTCUSD_EVT", timeframe=15)

    assert patterns
    assert pattern is not None and pattern["slug"] == "bull_flag"
    assert features
    assert coin_patterns
    assert regimes is not None and regimes["symbol"] == "BTCUSD_EVT"
    assert sectors
    assert sector_metrics["items"]
    assert cycles
    assert "compat.list_patterns.deprecated" in events
    assert "compat.get_pattern.deprecated" in events
    assert "compat.list_pattern_features.deprecated" in events
    assert "compat.list_coin_patterns.deprecated" in events
    assert "compat.get_coin_regimes.deprecated" in events
    assert "compat.list_sectors.deprecated" in events
    assert "compat.list_sector_metrics.deprecated" in events
    assert "compat.list_market_cycles.deprecated" in events


def test_patterns_legacy_compatibility_services_emit_deprecation_logs(db_session, monkeypatch) -> None:
    seed_pattern_api_state(db_session)
    events: list[str] = []

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)

    feature = update_pattern_feature(db_session, "pattern_context_engine", enabled=False)
    updated = update_pattern(db_session, "bull_flag", enabled=False, lifecycle_state=None, cpu_cost=0)

    assert feature is not None and feature["enabled"] is False
    assert updated is not None
    assert updated["enabled"] is False
    assert updated["lifecycle_state"] == "DISABLED"
    assert updated["cpu_cost"] == 1
    assert "compat.update_pattern_feature.deprecated" in events
    assert "compat.update_pattern.deprecated" in events
