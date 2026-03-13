from __future__ import annotations

import pytest
from sqlalchemy import select

from src.apps.cross_market.models import SectorMetric
from src.apps.market_data.models import Candle
from src.apps.market_data.candles import candle_close_timestamp
from src.apps.patterns.models import DiscoveredPattern, PatternFeature
from src.apps.patterns.domain.strategy import StrategyCandidate
from src.apps.patterns.task_services import (
    PatternDiscoveryService,
    PatternSignalContextService,
    PatternStrategyService,
)
from src.apps.signals.models import FinalSignal, InvestmentDecision, Signal, Strategy
from src.core.db.uow import SessionUnitOfWork
from tests.fusion_support import insert_signals
from tests.patterns_support import seed_pattern_api_state, seed_pattern_catalog_metadata


@pytest.mark.asyncio
async def test_pattern_signal_context_service_enriches_rows_and_handles_missing_scope(
    async_db_session, db_session
) -> None:
    seeded = seed_pattern_api_state(db_session)
    btc = seeded["btc"]
    timestamp = seeded["signal_timestamp"]

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await PatternSignalContextService(uow).enrich(
            coin_id=int(btc.id),
            timeframe=15,
            candle_timestamp=timestamp,
        )

    assert result["status"] == "ok"
    assert result["context"]["status"] == "ok"
    assert result["decision"]["status"] in {"ok", "skipped"}
    assert result["final_signal"]["status"] in {"ok", "skipped"}

    rows = (
        await async_db_session.execute(
            select(Signal).where(
                Signal.coin_id == int(btc.id),
                Signal.timeframe == 15,
                Signal.candle_timestamp == timestamp,
            )
        )
    ).scalars().all()
    assert rows
    assert all(float(row.priority_score or 0.0) > 0.0 for row in rows)
    assert all(float(row.context_score or 0.0) > 0.0 for row in rows)
    assert all(float(row.regime_alignment or 0.0) > 0.0 for row in rows)

    async with SessionUnitOfWork(async_db_session) as uow:
        missing = await PatternSignalContextService(uow).enrich_context_only(
            coin_id=int(btc.id),
            timeframe=240,
        )

    assert missing["reason"] == "signals_not_found"


@pytest.mark.asyncio
async def test_pattern_discovery_service_replaces_discovered_patterns_and_respects_feature_flag(
    async_db_session, db_session, monkeypatch
) -> None:
    seed_pattern_catalog_metadata(db_session)
    seed_pattern_api_state(db_session)
    monkeypatch.setattr("src.apps.patterns.task_service_market._window_signature", lambda _closes: "shared-window")

    async with SessionUnitOfWork(async_db_session) as uow:
        refreshed = await PatternDiscoveryService(uow).refresh()

    assert refreshed["status"] == "ok"
    assert refreshed["patterns"] > 0
    rows = (await async_db_session.execute(select(DiscoveredPattern))).scalars().all()
    assert rows

    feature = await async_db_session.get(PatternFeature, "pattern_discovery_engine")
    assert feature is not None
    feature.enabled = False
    await async_db_session.commit()

    async with SessionUnitOfWork(async_db_session) as uow:
        skipped = await PatternDiscoveryService(uow).refresh()

    assert skipped["reason"] == "pattern_discovery_disabled"


@pytest.mark.asyncio
async def test_pattern_strategy_service_refreshes_current_runtime_path(async_db_session, db_session, monkeypatch) -> None:
    seed_pattern_catalog_metadata(db_session)
    seeded = seed_pattern_api_state(db_session)
    btc = seeded["btc"]
    timestamp = seeded["signal_timestamp"]
    monkeypatch.setattr(
        "src.apps.patterns.task_service_market._signal_outcome",
        lambda **_kwargs: (0.04, -0.02, True),
    )
    monkeypatch.setattr(
        "src.apps.patterns.task_service_market._context_from_window",
        lambda **_kwargs: ("bull_trend", "MARKUP"),
    )
    monkeypatch.setattr(
        "src.apps.patterns.task_service_market._strategy_enabled",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr("src.apps.patterns.task_service_market.MIN_DISCOVERY_SAMPLE", 1)
    monkeypatch.setattr(
        "src.apps.patterns.task_service_market._candidate_definitions",
        lambda **_kwargs: [
            StrategyCandidate(
                timeframe=15,
                tokens=("bull_flag",),
                regime="bull_trend",
                sector="store_of_value",
                cycle="MARKUP",
                min_confidence=0.8,
            )
        ],
    )

    db_session.add(
        SectorMetric(
            sector_id=int(btc.sector_id),
            timeframe=15,
            sector_strength=0.88,
            relative_strength=0.74,
            capital_flow=0.57,
            avg_price_change_24h=4.9,
            avg_volume_change_24h=16.0,
            volatility=0.044,
            trend="up",
            updated_at=timestamp,
        )
    )
    candles = db_session.scalars(
        select(Candle)
        .where(Candle.coin_id == int(btc.id), Candle.timeframe == 15)
        .order_by(Candle.timestamp.asc())
    ).all()
    assert len(candles) >= 32
    for candle in candles[15:23]:
        insert_signals(
            db_session,
            coin_id=int(btc.id),
            timeframe=15,
            candle_timestamp=candle_close_timestamp(candle.timestamp, 15),
            items=[
                ("pattern_bull_flag", 0.84),
                ("pattern_breakout_retest", 0.81),
            ],
        )
    db_session.commit()

    async with SessionUnitOfWork(async_db_session) as uow:
        refreshed = await PatternStrategyService(uow).refresh()

    assert refreshed["status"] == "ok"
    assert refreshed["strategies"]["status"] == "ok"
    assert refreshed["strategies"]["strategies"] > 0
    assert refreshed["decisions"]["candidates"] >= 1
    assert refreshed["final_signals"]["candidates"] >= 1

    strategies = (await async_db_session.execute(select(Strategy).where(Strategy.enabled.is_(True)))).scalars().all()
    decisions = (await async_db_session.execute(select(InvestmentDecision))).scalars().all()
    final_signals = (await async_db_session.execute(select(FinalSignal))).scalars().all()
    assert strategies
    assert decisions
    assert final_signals
