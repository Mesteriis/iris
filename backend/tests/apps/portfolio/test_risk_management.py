import pytest
from sqlalchemy import select
from src.apps.portfolio.models import PortfolioPosition
from src.apps.portfolio.services import PortfolioService, PortfolioSideEffectDispatcher
from src.core.db.uow import SessionUnitOfWork
from src.core.settings import get_settings

from tests.fusion_support import create_test_coin, upsert_coin_metrics
from tests.portfolio_support import create_market_decision, create_sector


@pytest.mark.asyncio
async def test_risk_management_blocks_new_position_when_max_positions_reached(async_db_session, db_session) -> None:
    settings = get_settings()
    for index in range(settings.portfolio_max_positions):
        coin = create_test_coin(db_session, symbol=f"BTC{index:02d}_EVT", name=f"Coin {index}")
        upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)
        create_market_decision(
            db_session,
            coin_id=int(coin.id),
            timeframe=15,
            decision="BUY",
            confidence=0.8,
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

    blocked = create_test_coin(db_session, symbol="SOLUSD_EVT", name="Solana Event Test")
    upsert_coin_metrics(db_session, coin_id=int(blocked.id), regime="bull_trend", timeframe=15)
    create_market_decision(
        db_session,
        coin_id=int(blocked.id),
        timeframe=15,
        decision="BUY",
        confidence=0.9,
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await PortfolioService(uow).evaluate_portfolio_action(
            coin_id=int(blocked.id),
            timeframe=15,
            emit_events=False,
        )
        await uow.commit()
        await PortfolioSideEffectDispatcher().apply_action_result(result)

    db_session.expire_all()

    assert result.status == "ok"
    assert result.action == "HOLD_POSITION"
    position = db_session.scalar(
        select(PortfolioPosition)
        .where(PortfolioPosition.coin_id == int(blocked.id), PortfolioPosition.timeframe == 15)
        .limit(1)
    )
    assert position is None


@pytest.mark.asyncio
async def test_risk_management_blocks_new_sector_when_exposure_limit_hit(async_db_session, db_session) -> None:
    settings = get_settings()
    sector = create_sector(db_session, name="Infrastructure")
    leader = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    leader.sector_id = int(sector.id)
    db_session.commit()
    upsert_coin_metrics(db_session, coin_id=int(leader.id), regime="bull_trend", timeframe=15)
    create_market_decision(
        db_session,
        coin_id=int(leader.id),
        timeframe=15,
        decision="BUY",
        confidence=1.0,
    )
    async with SessionUnitOfWork(async_db_session) as uow:
        first = await PortfolioService(uow).evaluate_portfolio_action(
            coin_id=int(leader.id),
            timeframe=15,
            emit_events=False,
        )
        await uow.commit()
        await PortfolioSideEffectDispatcher().apply_action_result(first)
    db_session.expire_all()
    assert first.action == "OPEN_POSITION"

    original_limit = settings.portfolio_max_sector_exposure
    settings.portfolio_max_sector_exposure = 0.01
    try:
        follower = create_test_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test")
        follower.sector_id = int(sector.id)
        db_session.commit()
        upsert_coin_metrics(db_session, coin_id=int(follower.id), regime="bull_trend", timeframe=15)
        create_market_decision(
            db_session,
            coin_id=int(follower.id),
            timeframe=15,
            decision="BUY",
            confidence=0.9,
        )

        async with SessionUnitOfWork(async_db_session) as uow:
            result = await PortfolioService(uow).evaluate_portfolio_action(
                coin_id=int(follower.id),
                timeframe=15,
                emit_events=False,
            )
            await uow.commit()
            await PortfolioSideEffectDispatcher().apply_action_result(result)
        db_session.expire_all()
        assert result.action == "HOLD_POSITION"
    finally:
        settings.portfolio_max_sector_exposure = original_limit
