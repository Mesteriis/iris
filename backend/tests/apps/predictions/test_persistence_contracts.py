from __future__ import annotations

import importlib.util
from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest
from sqlalchemy import select

from src.apps.cross_market.models import CoinRelation
from src.apps.predictions.models import MarketPrediction
from src.apps.predictions.query_services import PredictionQueryService
from src.apps.predictions.services import PredictionService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork
from tests.cross_market_support import DEFAULT_START, create_cross_market_coin


@pytest.mark.asyncio
async def test_prediction_query_returns_immutable_read_models(async_db_session, seeded_api_state) -> None:
    rows = await PredictionQueryService(async_db_session).list_predictions(limit=10, status="confirmed")

    assert rows
    item = rows[0]
    assert item.leader_symbol == "BTCUSD_EVT"
    with pytest.raises(FrozenInstanceError):
        item.status = "pending"


@pytest.mark.asyncio
async def test_prediction_service_defers_commit_to_uow(async_db_session, db_session) -> None:
    leader = create_cross_market_coin(
        db_session,
        symbol="BTCUSD_EVT",
        name="Bitcoin Event Test",
        sector_name="store_of_value",
    )
    follower = create_cross_market_coin(
        db_session,
        symbol="ETHUSD_EVT",
        name="Ethereum Event Test",
        sector_name="smart_contract",
    )
    db_session.add(
        CoinRelation(
            leader_coin_id=int(leader.id),
            follower_coin_id=int(follower.id),
            correlation=0.82,
            lag_hours=4,
            confidence=0.78,
            updated_at=DEFAULT_START,
        )
    )
    db_session.commit()

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await PredictionService(uow).create_market_predictions(
            leader_coin_id=int(leader.id),
            prediction_event="leader_breakout",
            expected_move="up",
            base_confidence=0.8,
        )
        assert result.created == 1
        visible_before_commit = db_session.scalar(
            select(MarketPrediction).where(MarketPrediction.leader_coin_id == int(leader.id)).limit(1)
        )
        assert visible_before_commit is None

    db_session.expire_all()
    visible_after_rollback = db_session.scalar(
        select(MarketPrediction).where(MarketPrediction.leader_coin_id == int(leader.id)).limit(1)
    )
    assert visible_after_rollback is None


@pytest.mark.asyncio
async def test_prediction_persistence_logs_cover_query_service_and_uow(async_db_session, monkeypatch) -> None:
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
        await PredictionQueryService(uow.session).list_predictions(limit=5, status=None)

    assert "uow.begin" in events
    assert "query.list_predictions" in events
    assert "uow.rollback_uncommitted" in events


def test_prediction_engine_module_is_removed() -> None:
    assert importlib.util.find_spec("src.apps.predictions.engine") is None
