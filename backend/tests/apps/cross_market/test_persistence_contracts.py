import importlib.util
from dataclasses import FrozenInstanceError

import pytest
from sqlalchemy import select
from src.apps.cross_market.models import CoinRelation
from src.apps.cross_market.query_services import CrossMarketQueryService
from src.apps.cross_market.read_models import LeaderDecisionReadModel, RelationComputationContextReadModel
from src.apps.cross_market.services import CrossMarketService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork

from tests.cross_market_support import (
    DEFAULT_START,
    correlated_close_series,
    create_cross_market_coin,
    generate_close_series,
    seed_candles,
    set_market_metrics,
)


@pytest.mark.asyncio
async def test_cross_market_query_returns_immutable_read_models(async_db_session, db_session) -> None:
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
            correlation=0.83,
            lag_hours=4,
            confidence=0.78,
            updated_at=DEFAULT_START,
        )
    )
    db_session.commit()
    set_market_metrics(
        db_session,
        coin_id=int(leader.id),
        regime="bull_trend",
        price_change_24h=6.2,
        volume_change_24h=28.0,
        market_cap=900_000_000_000.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(follower.id),
        regime="bull_trend",
        price_change_24h=3.7,
        volume_change_24h=16.0,
        market_cap=350_000_000_000.0,
    )

    query_service = CrossMarketQueryService(async_db_session)
    context = await query_service.get_relation_computation_context(
        follower_coin_id=int(follower.id),
        preferred_symbols=("BTCUSD_EVT",),
        limit=4,
    )
    leader_context = await query_service.get_leader_detection_context(coin_id=int(leader.id))
    leader_decision = await query_service.get_latest_leader_decision(leader_coin_id=int(leader.id), timeframe=60)
    aggregates = await query_service.list_sector_momentum_aggregates()

    assert context is not None
    assert isinstance(context, RelationComputationContextReadModel)
    assert context.follower_coin_id == int(follower.id)
    assert "BTCUSD_EVT" in {item.symbol for item in context.candidates}
    assert leader_context is not None
    assert leader_context.symbol == "BTCUSD_EVT"
    assert leader_decision is not None
    assert isinstance(leader_decision, LeaderDecisionReadModel)
    assert leader_decision.decision == "BUY"
    assert any(item.sector_id == int(leader.sector_id) for item in aggregates)
    with pytest.raises(FrozenInstanceError):
        context.follower_symbol = "changed"
    with pytest.raises(FrozenInstanceError):
        context.candidates[0].symbol = "changed"
    with pytest.raises(FrozenInstanceError):
        leader_context.symbol = "changed"
    with pytest.raises(FrozenInstanceError):
        leader_decision.confidence = 0.5


@pytest.mark.asyncio
async def test_cross_market_service_batches_leader_candle_reads(async_db_session, db_session, monkeypatch) -> None:
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
    alternate_leader = create_cross_market_coin(
        db_session,
        symbol="SOLUSD_EVT",
        name="Solana Event Test",
        sector_name="smart_contract",
    )
    leader_returns = [
        0.01 if index % 12 in {1, 2, 3} else -0.006 if index % 12 in {8, 9} else 0.0015 for index in range(220)
    ]
    leader_closes = generate_close_series(start_price=110.0, returns=leader_returns)
    follower_closes = correlated_close_series(leader_returns=leader_returns, lag_bars=4, start_price=62.0)
    alternate_closes = generate_close_series(
        start_price=42.0,
        returns=[0.002 if index % 3 else -0.001 for index in range(220)],
    )
    seed_candles(db_session, coin=leader, interval="1h", closes=leader_closes, start=DEFAULT_START)
    seed_candles(db_session, coin=follower, interval="1h", closes=follower_closes, start=DEFAULT_START)
    seed_candles(db_session, coin=alternate_leader, interval="1h", closes=alternate_closes, start=DEFAULT_START)
    set_market_metrics(
        db_session,
        coin_id=int(leader.id),
        regime="bull_trend",
        price_change_24h=6.8,
        volume_change_24h=31.0,
        market_cap=950_000_000_000.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(follower.id),
        regime="bull_trend",
        price_change_24h=4.1,
        volume_change_24h=18.0,
        market_cap=420_000_000_000.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(alternate_leader.id),
        regime="bull_trend",
        price_change_24h=1.3,
        volume_change_24h=11.0,
        market_cap=120_000_000_000.0,
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        service = CrossMarketService(uow)
        monkeypatch.setattr(
            "src.apps.cross_market.services.cache_correlation_snapshot_async",
            lambda **_: __import__("asyncio").sleep(0),
        )
        single_calls: list[int] = []
        batch_calls: list[tuple[int, ...]] = []
        original_fetch_points = service._candles.fetch_points
        original_fetch_points_for_coin_ids = service._candles.fetch_points_for_coin_ids

        async def _counted_fetch_points(*, coin_id: int, timeframe: int, limit: int):
            single_calls.append(coin_id)
            return await original_fetch_points(coin_id=coin_id, timeframe=timeframe, limit=limit)

        async def _counted_fetch_points_for_coin_ids(*, coin_ids: list[int], timeframe: int, limit: int):
            batch_calls.append(tuple(coin_ids))
            return await original_fetch_points_for_coin_ids(coin_ids=coin_ids, timeframe=timeframe, limit=limit)

        monkeypatch.setattr(service._candles, "fetch_points", _counted_fetch_points)
        monkeypatch.setattr(service._candles, "fetch_points_for_coin_ids", _counted_fetch_points_for_coin_ids)

        result = await service.process_event(
            coin_id=int(follower.id),
            timeframe=60,
            event_type="candle_closed",
            payload={},
            emit_events=False,
        )
        await uow.commit()

    relations = (
        (
            await async_db_session.execute(
                select(CoinRelation)
                .where(CoinRelation.follower_coin_id == int(follower.id))
                .order_by(CoinRelation.confidence.desc(), CoinRelation.correlation.desc())
            )
        )
        .scalars()
        .all()
    )

    assert result.relations.status == "ok"
    assert len(relations) >= 1
    assert single_calls == [int(follower.id)]
    assert len(batch_calls) == 1
    assert int(leader.id) in batch_calls[0]
    assert int(alternate_leader.id) in batch_calls[0]


@pytest.mark.asyncio
async def test_cross_market_persistence_logs_cover_query_repo_service_and_uow(
    async_db_session, db_session, monkeypatch
) -> None:
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
    leader_returns = [
        0.008 if index % 10 in {1, 2, 3} else -0.005 if index % 10 in {7, 8} else 0.001 for index in range(220)
    ]
    seed_candles(
        db_session,
        coin=leader,
        interval="1h",
        closes=generate_close_series(start_price=105.0, returns=leader_returns),
        start=DEFAULT_START,
    )
    seed_candles(
        db_session,
        coin=follower,
        interval="1h",
        closes=correlated_close_series(leader_returns=leader_returns, lag_bars=3, start_price=58.0),
        start=DEFAULT_START,
    )
    set_market_metrics(
        db_session,
        coin_id=int(leader.id),
        regime="bull_trend",
        price_change_24h=5.9,
        volume_change_24h=27.0,
        market_cap=910_000_000_000.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(follower.id),
        regime="bull_trend",
        price_change_24h=3.9,
        volume_change_24h=17.0,
        market_cap=390_000_000_000.0,
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
    monkeypatch.setattr(
        "src.apps.cross_market.services.cache_correlation_snapshot_async", lambda **_: __import__("asyncio").sleep(0)
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await CrossMarketService(uow).process_event(
            coin_id=int(follower.id),
            timeframe=60,
            event_type="candle_closed",
            payload={},
            emit_events=False,
        )
        await uow.commit()

    assert result.relations.status == "ok"
    assert "uow.begin" in events
    assert "service.process_cross_market_event" in events
    assert "query.get_cross_market_relation_context" in events
    assert "repo.fetch_market_data_candle_points" in events
    assert "repo.fetch_market_data_candle_points_for_coin_ids" in events
    assert "repo.upsert_cross_market_relations" in events
    assert "repo.upsert_cross_market_sector_metrics" in events
    assert "uow.commit" in events


def test_cross_market_modules_export_no_public_sync_wrappers() -> None:
    assert importlib.util.find_spec("src.apps.cross_market.engine") is None
