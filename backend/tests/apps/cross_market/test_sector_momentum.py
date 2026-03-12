from __future__ import annotations

from app.apps.cross_market.engine import refresh_sector_momentum
from app.apps.cross_market.models import SectorMetric
from tests.cross_market_support import create_cross_market_coin, set_market_metrics


def test_sector_momentum_refreshes_relative_strength_and_trend(db_session) -> None:
    sol = create_cross_market_coin(
        db_session,
        symbol="SOLUSD_EVT",
        name="Solana Event Test",
        sector_name="smart_contract",
    )
    eth = create_cross_market_coin(
        db_session,
        symbol="ETHUSD_EVT",
        name="Ethereum Event Test",
        sector_name="smart_contract",
    )
    aave = create_cross_market_coin(
        db_session,
        symbol="AAVEUSD_EVT",
        name="Aave Event Test",
        sector_name="defi",
    )
    uni = create_cross_market_coin(
        db_session,
        symbol="UNIUSD_EVT",
        name="Uniswap Event Test",
        sector_name="defi",
    )
    gaming = create_cross_market_coin(
        db_session,
        symbol="IMXUSD_EVT",
        name="Immutable Event Test",
        sector_name="gaming",
    )
    set_market_metrics(
        db_session,
        coin_id=int(sol.id),
        regime="bull_trend",
        price_change_24h=6.4,
        volume_change_24h=24.0,
        volatility=0.07,
        market_cap=120_000_000_000.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(eth.id),
        regime="bull_trend",
        price_change_24h=4.2,
        volume_change_24h=18.0,
        volatility=0.05,
        market_cap=380_000_000_000.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(aave.id),
        regime="bear_trend",
        price_change_24h=-3.4,
        volume_change_24h=-10.0,
        volatility=0.08,
        market_cap=2_000_000_000.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(uni.id),
        regime="bear_trend",
        price_change_24h=-2.2,
        volume_change_24h=-6.0,
        volatility=0.06,
        market_cap=6_000_000_000.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(gaming.id),
        regime="sideways_range",
        price_change_24h=0.4,
        volume_change_24h=-3.0,
        volatility=0.03,
        market_cap=4_500_000_000.0,
    )

    result = refresh_sector_momentum(db_session, timeframe=60, emit_events=False)

    smart_contract = db_session.get(SectorMetric, (int(sol.sector_id), 60))
    defi = db_session.get(SectorMetric, (int(aave.sector_id), 60))
    sideways = db_session.get(SectorMetric, (int(gaming.sector_id), 60))
    assert result["status"] == "ok"
    assert result["updated"] >= 2
    assert smart_contract is not None
    assert defi is not None
    assert sideways is not None
    assert float(smart_contract.avg_price_change_24h) > 5.0
    assert float(smart_contract.avg_volume_change_24h) > 20.0
    assert smart_contract.trend == "bullish"
    assert float(defi.avg_price_change_24h) < -2.5
    assert float(defi.avg_volume_change_24h) < -7.0
    assert defi.trend == "bearish"
    assert -1.0 < float(sideways.avg_price_change_24h) < 1.0
    assert float(sideways.avg_volume_change_24h) < 0.0
    assert sideways.trend == "sideways"
    assert float(smart_contract.relative_strength) > float(defi.relative_strength)
