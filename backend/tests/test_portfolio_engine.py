from __future__ import annotations

import multiprocessing
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.events.publisher import flush_publisher, publish_event
from app.events.runner import run_worker_loop
from app.models.portfolio_action import PortfolioAction
from app.models.portfolio_position import PortfolioPosition
from app.portfolio.engine import evaluate_portfolio_action
from tests.fusion_support import create_test_coin, upsert_coin_metrics
from tests.portfolio_support import create_market_decision


def test_portfolio_engine_opens_position_from_buy_decision(db_session) -> None:
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)
    create_market_decision(
        db_session,
        coin_id=int(coin.id),
        timeframe=15,
        decision="BUY",
        confidence=0.82,
    )

    result = evaluate_portfolio_action(
        db_session,
        coin_id=int(coin.id),
        timeframe=15,
        emit_events=False,
    )

    assert result["status"] == "ok"
    assert result["action"] == "OPEN_POSITION"
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

    ctx = multiprocessing.get_context("spawn")
    worker = ctx.Process(
        target=run_worker_loop,
        args=("portfolio_workers",),
        daemon=True,
    )
    worker.start()
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
        worker.terminate()
        worker.join(timeout=2.0)
