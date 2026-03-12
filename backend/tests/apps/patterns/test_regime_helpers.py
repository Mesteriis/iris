from __future__ import annotations

from types import SimpleNamespace

from src.apps.patterns.domain.regime import (
    MARKET_REGIMES,
    calculate_regime_map,
    compute_live_regimes,
    detect_market_regime,
    primary_regime,
    read_regime_details,
    serialize_regime_map,
)
from tests.cross_market_support import DEFAULT_START, create_cross_market_coin, generate_close_series, seed_candles


def test_regime_helpers_cover_maps_and_invalid_payloads() -> None:
    high_volatility, _ = detect_market_regime(
        {
            "price_current": 100.0,
            "adx_14": 24.0,
            "bb_width": 0.09,
            "atr_14": 3.5,
            "prev_atr_14": 3.4,
        }
    )
    default_sideways, confidence = detect_market_regime(
        {
            "price_current": 100.0,
            "adx_14": 22.0,
            "bb_width": 0.05,
            "atr_14": 1.5,
            "prev_atr_14": 1.49,
            "price_change_7d": 1.0,
        }
    )
    assert high_volatility == "high_volatility"
    assert default_sideways == "sideways_range"
    assert confidence == 0.65
    low_adx_sideways, low_adx_confidence = detect_market_regime(
        {
            "price_current": 100.0,
            "adx_14": 18.0,
            "bb_width": 0.05,
            "atr_14": 1.8,
            "prev_atr_14": 1.79,
        }
    )
    assert low_adx_sideways == "sideways_range"
    assert low_adx_confidence == 0.72

    snapshots = {
        15: SimpleNamespace(
            price_current=100.0,
            ema_50=101.0,
            ema_200=99.0,
            sma_200=99.0,
            adx_14=32.0,
            bb_width=0.05,
            prev_bb_width=0.04,
            atr_14=2.0,
            prev_atr_14=1.9,
        ),
        1440: SimpleNamespace(
            price_current=100.0,
            ema_50=98.0,
            ema_200=101.0,
            sma_200=101.0,
            adx_14=30.0,
            bb_width=0.06,
            prev_bb_width=0.05,
            atr_14=2.2,
            prev_atr_14=2.1,
        ),
    }
    regime_map = calculate_regime_map(snapshots, volatility=0.05, price_change_7d=-6.0)
    assert primary_regime(regime_map) == regime_map[1440].regime
    assert serialize_regime_map(regime_map)["15"]["regime"] in MARKET_REGIMES
    assert primary_regime({}) is None

    assert read_regime_details(None, 15) is None
    assert read_regime_details({"60": {}}, 15) is None
    assert read_regime_details({"15": {"regime": 123, "confidence": 0.5}}, 15) is None
    invalid_confidence = read_regime_details({"15": {"regime": "bull_trend", "confidence": "bad"}}, 15)
    assert invalid_confidence is not None
    assert invalid_confidence.confidence == 0.0


def test_compute_live_regimes_uses_seeded_candles(db_session) -> None:
    coin = create_cross_market_coin(
        db_session,
        symbol="BTCUSD_EVT",
        name="Bitcoin Event Test",
        sector_name="store_of_value",
    )
    seed_candles(
        db_session,
        coin=coin,
        interval="15m",
        closes=generate_close_series(start_price=100.0, returns=[0.002] * 40),
        start=DEFAULT_START,
    )
    seed_candles(
        db_session,
        coin=coin,
        interval="1h",
        closes=generate_close_series(start_price=100.0, returns=[0.003] * 30),
        start=DEFAULT_START,
    )

    rows = compute_live_regimes(db_session, int(coin.id))
    assert {row.timeframe for row in rows} == {15, 60}
    assert all(row.regime in MARKET_REGIMES for row in rows)
    assert all(row.confidence > 0 for row in rows)
