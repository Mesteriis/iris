from __future__ import annotations

from datetime import timedelta
from dataclasses import FrozenInstanceError

import pytest
from sqlalchemy import select

import src.apps.signals.services as signal_services_module
from src.apps.signals.models import MarketDecision, Signal, SignalHistory
from src.apps.signals.query_services import SignalQueryService
from src.apps.signals.services import SignalFusionService, SignalHistoryService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork
from tests.cross_market_support import DEFAULT_START, seed_candles
from tests.factories.seeds import SignalSeedFactory
from tests.fusion_support import create_test_coin, insert_signals, replace_pattern_statistics, upsert_coin_metrics


@pytest.mark.asyncio
async def test_signal_query_returns_immutable_read_models(async_db_session, seeded_api_state) -> None:
    del seeded_api_state
    rows = await SignalQueryService(async_db_session).list_signals(symbol="BTCUSD_EVT", limit=10)

    assert rows
    item = rows[0]
    assert item.symbol == "BTCUSD_EVT"
    assert isinstance(item.cluster_membership, tuple)
    with pytest.raises(FrozenInstanceError):
        item.signal_type = "changed"


@pytest.mark.asyncio
async def test_signal_persistence_logs_cover_query_service_and_uow(async_db_session) -> None:
    events: list[str] = []

    def _debug(message: str, *args, **kwargs) -> None:
        del args, kwargs
        events.append(message)

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    original_debug = PERSISTENCE_LOGGER.debug
    original_log = PERSISTENCE_LOGGER.log
    PERSISTENCE_LOGGER.debug = _debug
    PERSISTENCE_LOGGER.log = _log
    try:
        async with SessionUnitOfWork(async_db_session) as uow:
            await SignalQueryService(uow.session).list_signals(limit=5)
    finally:
        PERSISTENCE_LOGGER.debug = original_debug
        PERSISTENCE_LOGGER.log = original_log

    assert "uow.begin" in events
    assert "query.list_signals" in events
    assert "uow.rollback_uncommitted" in events


@pytest.mark.asyncio
async def test_signal_fusion_service_defers_commit_to_uow(async_db_session, db_session) -> None:
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    coin_id = int(coin.id)
    upsert_coin_metrics(db_session, coin_id=coin_id, regime="bull_trend")
    replace_pattern_statistics(
        db_session,
        timeframe=15,
        rows=[
            ("bull_flag", "all", 0.71, 50),
            ("breakout_retest", "all", 0.67, 50),
        ],
    )
    insert_signals(
        db_session,
        coin_id=coin_id,
        timeframe=15,
        candle_timestamp=coin.created_at,
        items=[
            ("pattern_bull_flag", 0.81),
            ("pattern_breakout_retest", 0.79),
        ],
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await SignalFusionService(uow).evaluate_market_decision(
            coin_id=coin_id,
            timeframe=15,
            trigger_timestamp=coin.created_at,
            emit_event=False,
        )
        assert result.status == "ok"
        visible_before_commit = db_session.scalar(
            select(MarketDecision).where(MarketDecision.coin_id == coin_id, MarketDecision.timeframe == 15).limit(1)
        )
        assert visible_before_commit is None

    db_session.expire_all()
    visible_after_rollback = db_session.scalar(
        select(MarketDecision).where(MarketDecision.coin_id == coin_id, MarketDecision.timeframe == 15).limit(1)
    )
    assert visible_after_rollback is None


@pytest.mark.asyncio
async def test_signal_fusion_persistence_logs_cover_service_repo_and_uow(async_db_session, db_session, monkeypatch) -> None:
    coin = create_test_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test")
    coin_id = int(coin.id)
    upsert_coin_metrics(db_session, coin_id=coin_id, regime="bull_trend")
    replace_pattern_statistics(db_session, timeframe=15, rows=[("bull_flag", "all", 0.7, 50)])
    insert_signals(
        db_session,
        coin_id=coin_id,
        timeframe=15,
        candle_timestamp=coin.created_at,
        items=[("pattern_bull_flag", 0.76)],
    )
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
        await SignalFusionService(uow).evaluate_market_decision(
            coin_id=coin_id,
            timeframe=15,
            trigger_timestamp=coin.created_at,
            emit_event=False,
        )

    assert "uow.begin" in events
    assert "service.evaluate_market_decision" in events
    assert "repo.list_recent_fusion_signals" in events
    assert "uow.rollback_uncommitted" in events


@pytest.mark.asyncio
async def test_signal_history_service_defers_commit_to_uow(async_db_session, db_session) -> None:
    coin = create_test_coin(db_session, symbol="SOLUSD_EVT", name="Solana Event Test")
    seed_candles(
        db_session,
        coin=coin,
        interval="1h",
        closes=[100.0 + index for index in range(80)],
        start=DEFAULT_START,
    )
    signal_timestamp = DEFAULT_START + timedelta(hours=1)
    seed = SignalSeedFactory.build(
        signal_type="golden_cross",
        confidence=0.72,
        priority_score=100.0,
        context_score=1.0,
        regime_alignment=1.0,
        candle_timestamp=signal_timestamp,
        created_at=signal_timestamp,
    )
    db_session.add(Signal(coin_id=int(coin.id), timeframe=60, **seed.__dict__))
    db_session.commit()

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await SignalHistoryService(uow).refresh_recent_history(coin_id=int(coin.id), timeframe=60)
        assert result.status == "ok"
        assert result.rows == 1
        visible_before_commit = db_session.scalar(
            select(SignalHistory)
            .where(SignalHistory.coin_id == int(coin.id), SignalHistory.timeframe == 60)
            .limit(1)
        )
        assert visible_before_commit is None

    db_session.expire_all()
    visible_after_rollback = db_session.scalar(
        select(SignalHistory)
        .where(SignalHistory.coin_id == int(coin.id), SignalHistory.timeframe == 60)
        .limit(1)
    )
    assert visible_after_rollback is None


@pytest.mark.asyncio
async def test_signal_history_persistence_logs_cover_service_repo_and_uow(async_db_session, db_session, monkeypatch) -> None:
    coin = create_test_coin(db_session, symbol="AVAXUSD_EVT", name="Avalanche Event Test")
    seed_candles(
        db_session,
        coin=coin,
        interval="1h",
        closes=[100.0 + index for index in range(80)],
        start=DEFAULT_START,
    )
    signal_timestamp = DEFAULT_START + timedelta(hours=1)
    seed = SignalSeedFactory.build(
        signal_type="golden_cross",
        confidence=0.72,
        priority_score=100.0,
        context_score=1.0,
        regime_alignment=1.0,
        candle_timestamp=signal_timestamp,
        created_at=signal_timestamp,
    )
    db_session.add(Signal(coin_id=int(coin.id), timeframe=60, **seed.__dict__))
    db_session.commit()
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
        await SignalHistoryService(uow).refresh_recent_history(coin_id=int(coin.id), timeframe=60)

    assert "uow.begin" in events
    assert "service.refresh_recent_signal_history" in events
    assert "repo.list_signal_history_signals" in events
    assert "repo.upsert_signal_history_rows" in events
    assert "uow.rollback_uncommitted" in events


def test_signal_services_exports_no_public_async_query_wrappers() -> None:
    forbidden_exports = (
        "get_coin_backtests_async",
        "get_coin_decision_async",
        "get_coin_final_signal_async",
        "get_coin_market_decision_async",
        "list_backtests_async",
        "list_decisions_async",
        "list_enriched_signals_async",
        "list_final_signals_async",
        "list_market_decisions_async",
        "list_strategies_async",
        "list_strategy_performance_async",
        "list_top_backtests_async",
        "list_top_decisions_async",
        "list_top_final_signals_async",
        "list_top_market_decisions_async",
        "list_top_signals_async",
    )

    for export_name in forbidden_exports:
        assert not hasattr(signal_services_module, export_name), export_name
