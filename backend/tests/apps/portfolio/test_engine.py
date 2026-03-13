from __future__ import annotations

import multiprocessing
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.apps.portfolio.services import PortfolioService, PortfolioSideEffectDispatcher
from src.core.db.session import SessionLocal
from src.core.db.uow import SessionUnitOfWork
from src.runtime.control_plane.worker import create_topology_dispatcher_consumer
from src.runtime.streams.publisher import flush_publisher, publish_event
from src.runtime.streams.runner import run_worker_loop
from src.apps.portfolio.models import PortfolioAction
from src.apps.portfolio.models import PortfolioPosition
from tests.fusion_support import create_test_coin, upsert_coin_metrics
from tests.portfolio_support import create_market_decision


def _run_dispatcher_loop() -> None:
    consumer = create_topology_dispatcher_consumer()
    try:
        consumer.run()
    finally:
        consumer.close()


def _start_portfolio_pipeline_processes() -> tuple[multiprocessing.Process, multiprocessing.Process]:
    ctx = multiprocessing.get_context("spawn")
    dispatcher = ctx.Process(target=_run_dispatcher_loop, daemon=True)
    worker = ctx.Process(
        target=run_worker_loop,
        args=("portfolio_workers",),
        daemon=True,
    )
    dispatcher.start()
    worker.start()
    return dispatcher, worker


def _stop_processes(*processes: multiprocessing.Process) -> None:
    for process in processes:
        process.terminate()
    for process in processes:
        process.join(timeout=2.0)


@pytest.mark.asyncio
async def test_portfolio_engine_opens_position_from_buy_decision(async_db_session, db_session) -> None:
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)
    create_market_decision(
        db_session,
        coin_id=int(coin.id),
        timeframe=15,
        decision="BUY",
        confidence=0.82,
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await PortfolioService(uow).evaluate_portfolio_action(
            coin_id=int(coin.id),
            timeframe=15,
            emit_events=False,
        )
        await uow.commit()
        await PortfolioSideEffectDispatcher().apply_action_result(result)

    db_session.expire_all()

    assert result.status == "ok"
    assert result.action == "OPEN_POSITION"
    position = db_session.scalar(
        select(PortfolioPosition)
        .where(PortfolioPosition.coin_id == int(coin.id), PortfolioPosition.timeframe == 15)
        .limit(1)
    )
    assert position is not None
    assert position.status == "open"
    assert float(position.position_value) > 0
    assert position.stop_loss is not None
    assert position.take_profit is not None


@pytest.mark.asyncio
async def test_portfolio_worker_consumes_signal_fusion_decision_event(db_session, wait_until) -> None:
    coin = create_test_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test")
    upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)
    create_market_decision(
        db_session,
        coin_id=int(coin.id),
        timeframe=15,
        decision="BUY",
        confidence=0.76,
    )
    timestamp = datetime(2026, 3, 11, 14, 15, tzinfo=timezone.utc)

    dispatcher, worker = _start_portfolio_pipeline_processes()
    try:
        publish_event(
            "decision_generated",
            {
                "coin_id": int(coin.id),
                "timeframe": 15,
                "timestamp": timestamp,
                "decision": "BUY",
                "confidence": 0.76,
                "source": "signal_fusion",
            },
        )
        assert flush_publisher(timeout=5.0)

        def _action_created() -> bool:
            db = SessionLocal()
            try:
                count = db.scalar(
                    select(PortfolioAction.id)
                    .where(PortfolioAction.coin_id == int(coin.id))
                    .limit(1)
                )
                return count is not None
            finally:
                db.close()

        await wait_until(_action_created, timeout=10.0, interval=0.2)
    finally:
        _stop_processes(dispatcher, worker)
