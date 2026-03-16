import multiprocessing
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from src.apps.portfolio.models import PortfolioPosition
from src.apps.portfolio.query_services import PortfolioQueryService
from src.apps.portfolio.services import PortfolioService, PortfolioSideEffectDispatcher
from src.core.db.uow import SessionUnitOfWork
from src.runtime.control_plane.worker import create_topology_dispatcher_consumer
from src.runtime.streams.publisher import flush_publisher, publish_event
from src.runtime.streams.runner import run_worker_loop

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
async def test_portfolio_worker_consumes_signal_fusion_decision_event(async_db_session, db_session, settings, wait_until) -> None:
    coin = create_test_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test")
    upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)
    create_market_decision(
        db_session,
        coin_id=int(coin.id),
        timeframe=15,
        decision="BUY",
        confidence=0.76,
    )
    timestamp = datetime(2026, 3, 11, 14, 15, tzinfo=UTC)

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

        from redis import Redis

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await wait_until(
                lambda: any(
                    fields.get("event_type") == "portfolio_position_opened"
                    and int(fields.get("coin_id") or 0) == int(coin.id)
                    for _, fields in client.xrange(settings.event_stream_name, "-", "+")
                ),
                timeout=10.0,
                interval=0.2,
            )
        finally:
            client.close()

        await async_db_session.rollback()
        async_db_session.expire_all()
        actions = await PortfolioQueryService(async_db_session).list_actions(limit=20)
        assert any(action.coin_id == int(coin.id) for action in actions)
    finally:
        _stop_processes(dispatcher, worker)
