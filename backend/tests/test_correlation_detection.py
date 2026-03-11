from __future__ import annotations

from sqlalchemy import select

from app.analysis.cross_market_engine import update_coin_relations
from app.models.coin_relation import CoinRelation
from app.services.correlation_cache import read_cached_correlation
from tests.cross_market_support import (
    DEFAULT_START,
    correlated_close_series,
    create_cross_market_coin,
    generate_close_series,
    seed_candles,
    set_market_metrics,
)


def test_correlation_detection_finds_lagged_market_leader(db_session) -> None:
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
        0.009 if index % 11 in {1, 2, 3}
        else -0.006 if index % 11 in {7, 8}
        else 0.0015
        for index in range(220)
    ]
    leader_closes = generate_close_series(start_price=100.0, returns=leader_returns)
    follower_closes = correlated_close_series(
        leader_returns=leader_returns,
        lag_bars=4,
        start_price=55.0,
    )
    seed_candles(db_session, coin=leader, interval="1h", closes=leader_closes, start=DEFAULT_START)
    seed_candles(db_session, coin=follower, interval="1h", closes=follower_closes, start=DEFAULT_START)
    set_market_metrics(
        db_session,
        coin_id=int(leader.id),
        regime="bull_trend",
        price_change_24h=5.8,
        volume_change_24h=26.0,
        market_cap=900_000_000_000.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(follower.id),
        regime="bull_trend",
        price_change_24h=3.6,
        volume_change_24h=18.0,
        market_cap=400_000_000_000.0,
    )

    result = update_coin_relations(
        db_session,
        follower_coin_id=int(follower.id),
        timeframe=60,
        emit_events=False,
    )

    relation = db_session.scalar(
        select(CoinRelation)
        .where(
            CoinRelation.leader_coin_id == int(leader.id),
            CoinRelation.follower_coin_id == int(follower.id),
        )
        .limit(1)
    )
    assert result["status"] == "ok"
    assert relation is not None
    assert float(relation.correlation) >= 0.75
    assert int(relation.lag_hours) in {4, 5}
    assert float(relation.confidence) >= 0.5

    cached = read_cached_correlation(
        leader_coin_id=int(leader.id),
        follower_coin_id=int(follower.id),
    )
    assert cached is not None
    assert cached.lag_hours == int(relation.lag_hours)
    assert cached.correlation >= 0.75
