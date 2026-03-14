from __future__ import annotations

from src.apps.cross_market.engines import (
    CrossMarketLeaderDetectionInput,
    CrossMarketSectorMomentumAggregateInput,
    build_sector_momentum,
    evaluate_market_leader,
    evaluate_relation_candidate,
)


def test_relation_engine_detects_lagged_correlation() -> None:
    leader = tuple(100.0 + (index * 1.5) for index in range(60))
    follower = tuple(100.0 for _ in range(4)) + leader[:-4]
    result = evaluate_relation_candidate(
        leader_closes=leader,
        follower_closes=follower,
        timeframe=60,
        lookback=200,
        min_points=48,
        min_correlation=0.25,
        max_lag_hours=8,
    )

    assert result is not None
    assert result.correlation > 0.9
    assert result.lag_hours in {4, 5}
    assert result.confidence >= 0.2


def test_sector_engine_builds_ranked_rows() -> None:
    result = build_sector_momentum(
        aggregates=(
            CrossMarketSectorMomentumAggregateInput(
                sector_id=1,
                sector_name="smart_contract",
                avg_price_change_24h=6.0,
                avg_volume_change_24h=20.0,
                avg_volatility=0.05,
                capital_flow=0.4,
            ),
            CrossMarketSectorMomentumAggregateInput(
                sector_id=2,
                sector_name="defi",
                avg_price_change_24h=-3.0,
                avg_volume_change_24h=-8.0,
                avg_volatility=0.07,
                capital_flow=-0.2,
            ),
        ),
        timeframe=60,
    )

    assert len(result.rows) == 2
    assert result.rows[0].trend == "bullish"
    assert result.rows[1].trend == "bearish"
    assert result.top_sector is not None
    assert result.top_sector.sector_id == 1


def test_leader_engine_skips_when_thresholds_are_not_met() -> None:
    result = evaluate_market_leader(
        CrossMarketLeaderDetectionInput(
            activity_bucket="COLD",
            price_change_24h=0.8,
            volume_change_24h=4.0,
            market_regime="sideways_range",
        )
    )

    assert result.status == "skipped"
    assert result.reason == "leader_threshold_not_met"


def test_leader_engine_returns_direction_and_confidence() -> None:
    result = evaluate_market_leader(
        CrossMarketLeaderDetectionInput(
            activity_bucket="HOT",
            price_change_24h=-5.0,
            volume_change_24h=24.0,
            market_regime="bear_trend",
        )
    )

    assert result.status == "ok"
    assert result.direction == "down"
    assert result.confidence is not None
