from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.apps.cross_market.models import SectorMetric
from app.apps.indicators.models import CoinMetrics
from app.apps.patterns.models import PatternFeature
from app.apps.patterns.services import (
    _build_sector_narratives_async,
    _capital_wave_bucket,
    _cluster_membership_map_async,
    _coin_bar_return_async,
    _compute_live_regimes_async,
    _fetch_candle_points_async,
    _serialize_signal_rows_async,
    get_coin_regimes_async,
    list_coin_patterns_async,
    list_discovered_patterns_async,
    list_market_cycles_async,
    list_pattern_features_async,
    list_patterns_async,
    list_sector_metrics_async,
    list_sectors_async,
    update_pattern_async,
    update_pattern_feature_async,
)
from app.apps.patterns.selectors import _signal_select
from app.apps.signals.models import Signal


@pytest.mark.asyncio
async def test_pattern_async_services_cover_runtime_helpers(async_db_session, db_session, seeded_api_state) -> None:
    btc = seeded_api_state["btc"]
    eth = seeded_api_state["eth"]
    signal_timestamp = seeded_api_state["signal_timestamp"]

    rows = (
        await async_db_session.execute(
            _signal_select()
            .where(Signal.coin_id == int(btc.id), Signal.timeframe == 15)
            .order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc())
        )
    ).all()

    assert await _cluster_membership_map_async(async_db_session, []) == {}
    membership = await _cluster_membership_map_async(async_db_session, rows)
    assert membership[(int(btc.id), 15, signal_timestamp)] == ["pattern_cluster_breakout"]

    serialized = await _serialize_signal_rows_async(async_db_session, rows)
    assert serialized[0]["cluster_membership"] == ["pattern_cluster_breakout"]
    assert serialized[0]["market_regime"] == "bull_trend"
    assert serialized[0]["cycle_phase"] == "markup"

    candles = await _fetch_candle_points_async(async_db_session, coin_id=int(btc.id), timeframe=15, limit=25)
    assert len(candles) == 25
    assert candles[-1].timestamp > candles[0].timestamp

    short_return = await _coin_bar_return_async(async_db_session, coin_id=int(btc.id), timeframe=240)
    assert short_return == (None, None)
    price_change, volatility = await _coin_bar_return_async(async_db_session, coin_id=int(btc.id), timeframe=15)
    assert price_change is not None
    assert volatility is not None
    assert price_change > -1.0
    assert volatility >= 0.0

    live_regimes = await _compute_live_regimes_async(async_db_session, int(btc.id))
    assert len(live_regimes) == 1
    assert live_regimes[0].timeframe == 15

    assert _capital_wave_bucket(SimpleNamespace(symbol="BTCUSD", sector_id=1), None, top_sector_id=None) == "btc"
    assert _capital_wave_bucket(SimpleNamespace(symbol="ETHUSD", sector_id=1), SimpleNamespace(market_cap=20_000_000_000), top_sector_id=None) == "large_caps"
    assert _capital_wave_bucket(SimpleNamespace(symbol="ETHUSD", sector_id=77), SimpleNamespace(market_cap=5_000_000_000), top_sector_id=77) == "sector_leaders"
    assert _capital_wave_bucket(SimpleNamespace(symbol="ALTUSD", sector_id=1), SimpleNamespace(market_cap=2_000_000_000), top_sector_id=None) == "mid_caps"
    assert _capital_wave_bucket(SimpleNamespace(symbol="MICROUSD", sector_id=1), SimpleNamespace(market_cap=200_000_000), top_sector_id=None) == "micro_caps"

    db_session.add_all(
        [
            SectorMetric(
                sector_id=int(btc.sector_id),
                timeframe=15,
                sector_strength=0.91,
                relative_strength=0.83,
                capital_flow=0.62,
                avg_price_change_24h=5.4,
                avg_volume_change_24h=17.0,
                volatility=0.052,
                trend="up",
                updated_at=signal_timestamp,
            ),
            SectorMetric(
                sector_id=int(eth.sector_id),
                timeframe=15,
                sector_strength=0.55,
                relative_strength=0.41,
                capital_flow=0.31,
                avg_price_change_24h=2.2,
                avg_volume_change_24h=9.0,
                volatility=0.049,
                trend="up",
                updated_at=signal_timestamp,
            ),
        ]
    )
    db_session.commit()

    narratives = await _build_sector_narratives_async(async_db_session)
    narrative_15 = next(item for item in narratives if item.timeframe == 15)
    assert narrative_15.top_sector == "store_of_value"
    assert narrative_15.rotation_state == "btc_dominance_falling"
    assert narrative_15.capital_wave is not None


@pytest.mark.asyncio
async def test_pattern_async_services_cover_listing_update_and_regime_paths(async_db_session, db_session, seeded_api_state) -> None:
    patterns = await list_patterns_async(async_db_session)
    assert {"bull_flag", "breakout_retest"} <= {row["slug"] for row in patterns}

    features = await list_pattern_features_async(async_db_session)
    assert {"market_regime_engine", "pattern_context_engine"} <= {row["feature_slug"] for row in features}
    assert await update_pattern_feature_async(async_db_session, "missing_feature", enabled=False) is None
    assert (await update_pattern_feature_async(async_db_session, "pattern_context_engine", enabled=False))["enabled"] is False

    assert await update_pattern_async(async_db_session, "missing_pattern", enabled=True, lifecycle_state=None, cpu_cost=None) is None
    with pytest.raises(ValueError):
        await update_pattern_async(async_db_session, "bull_flag", enabled=True, lifecycle_state="invalid", cpu_cost=None)
    updated = await update_pattern_async(async_db_session, "bull_flag", enabled=False, lifecycle_state="experimental", cpu_cost=0)
    assert updated["enabled"] is False
    assert updated["lifecycle_state"] == "EXPERIMENTAL"
    assert updated["cpu_cost"] == 1
    active_update = await update_pattern_async(async_db_session, "breakout_retest", enabled=None, lifecycle_state="active", cpu_cost=None)
    assert active_update is not None
    assert active_update["lifecycle_state"] == "ACTIVE"
    cpu_only_update = await update_pattern_async(async_db_session, "breakout_retest", enabled=True, lifecycle_state=None, cpu_cost=2)
    assert cpu_only_update is not None
    assert cpu_only_update["cpu_cost"] == 2

    discovered = await list_discovered_patterns_async(async_db_session, timeframe=15, limit=1)
    assert discovered[0]["structure_hash"] == "cluster:bull_flag:15"
    assert (await list_discovered_patterns_async(async_db_session, limit=1))[0]["structure_hash"] == "cluster:bull_flag:15"

    coin_patterns = await list_coin_patterns_async(async_db_session, "btcusd_evt", limit=10)
    assert [row["signal_type"] for row in coin_patterns] == ["pattern_bull_flag", "pattern_cluster_breakout"]

    assert await get_coin_regimes_async(async_db_session, "missing_evt") is None
    direct_regime = await get_coin_regimes_async(async_db_session, "BTCUSD_EVT")
    assert direct_regime is not None
    assert direct_regime["canonical_regime"] == "bull_trend"
    assert direct_regime["items"][0]["timeframe"] == 15

    await update_pattern_feature_async(async_db_session, "market_regime_engine", enabled=False)
    disabled_regime = await get_coin_regimes_async(async_db_session, "BTCUSD_EVT")
    assert disabled_regime["canonical_regime"] is None
    assert disabled_regime["items"] == []

    feature = await async_db_session.get(PatternFeature, "market_regime_engine")
    assert feature is not None
    feature.enabled = True
    metrics = (await async_db_session.execute(select(CoinMetrics).where(CoinMetrics.coin_id == direct_regime["coin_id"]))).scalar_one()
    metrics.market_regime_details = None
    await async_db_session.commit()

    fallback_regime = await get_coin_regimes_async(async_db_session, "BTCUSD_EVT")
    assert fallback_regime["items"]

    sectors = await list_sectors_async(async_db_session)
    assert {row["name"] for row in sectors} >= {"store_of_value", "smart_contract", "high_beta"}

    signal_timestamp = seeded_api_state["signal_timestamp"]
    db_session.add_all(
        [
            SectorMetric(
                sector_id=int(seeded_api_state["btc"].sector_id),
                timeframe=15,
                sector_strength=0.91,
                relative_strength=0.83,
                capital_flow=0.62,
                avg_price_change_24h=5.4,
                avg_volume_change_24h=17.0,
                volatility=0.052,
                trend="up",
                updated_at=signal_timestamp,
            ),
            SectorMetric(
                sector_id=int(seeded_api_state["eth"].sector_id),
                timeframe=15,
                sector_strength=0.55,
                relative_strength=0.41,
                capital_flow=0.31,
                avg_price_change_24h=2.2,
                avg_volume_change_24h=9.0,
                volatility=0.049,
                trend="up",
                updated_at=signal_timestamp,
            ),
        ]
    )
    db_session.commit()

    sector_metrics_filtered = await list_sector_metrics_async(async_db_session, timeframe=15)
    assert [row["name"] for row in sector_metrics_filtered["items"]] == ["store_of_value", "smart_contract"]
    assert sector_metrics_filtered["narratives"][0]["timeframe"] == 15

    sector_metrics_all = await list_sector_metrics_async(async_db_session)
    assert len(sector_metrics_all["items"]) >= 4
    assert {item["timeframe"] for item in sector_metrics_all["narratives"]} >= {15, 60}

    cycles = await list_market_cycles_async(async_db_session, symbol="BTCUSD_EVT", timeframe=15)
    assert len(cycles) == 1
    assert cycles[0]["cycle_phase"] == "markup"
    assert await list_market_cycles_async(async_db_session)


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarResult(self._values)

    def scalar_one_or_none(self):
        return self._values


class _NarrativeSession:
    def __init__(self, responses):
        self._responses = iter(responses)

    async def execute(self, statement):
        del statement
        return _ExecuteResult(next(self._responses))


@pytest.mark.asyncio
async def test_pattern_async_sector_narrative_rotation_branches(monkeypatch) -> None:
    sector = SimpleNamespace(name="store_of_value")
    metric = SimpleNamespace(timeframe=15, relative_strength=0.8, sector=sector, sector_id=7)
    btc_coin = SimpleNamespace(id=1, symbol="BTCUSD", sector_id=7)
    alt_coin = SimpleNamespace(id=2, symbol="ALTUSD", sector_id=8)
    coin_metrics = {
        1: SimpleNamespace(coin_id=1, market_cap=900_000_000_000.0, volume_change_24h=12.0),
        2: SimpleNamespace(coin_id=2, market_cap=150_000_000_000.0, volume_change_24h=7.0),
    }

    async def _coin_bar_return(_db, *, coin_id: int, timeframe: int):
        del timeframe
        return (0.03 if coin_id == 1 else 0.02, 0.01)

    monkeypatch.setattr("app.apps.patterns.services._coin_bar_return_async", _coin_bar_return)

    none_session = _NarrativeSession(
        [
            [metric],
            None,
            [],
            [btc_coin, alt_coin],
            list(coin_metrics.values()),
        ]
    )
    none_narratives = await _build_sector_narratives_async(none_session)
    assert none_narratives[0].rotation_state is None

    rising_session = _NarrativeSession(
        [
            [metric],
            SimpleNamespace(market_cap=900_000_000_000.0, price_change_24h=6.0),
            [900_000_000_000.0, 150_000_000_000.0],
            [btc_coin, alt_coin],
            list(coin_metrics.values()),
        ]
    )
    rising_narratives = await _build_sector_narratives_async(rising_session)
    assert rising_narratives[0].rotation_state == "btc_dominance_rising"

    falling_session = _NarrativeSession(
        [
            [metric],
            SimpleNamespace(market_cap=300_000_000_000.0, price_change_24h=-4.0),
            [300_000_000_000.0, 900_000_000_000.0],
            [btc_coin, alt_coin],
            list(coin_metrics.values()),
        ]
    )
    falling_narratives = await _build_sector_narratives_async(falling_session)
    assert falling_narratives[0].rotation_state == "btc_dominance_falling"

    leadership_session = _NarrativeSession(
        [
            [metric],
            SimpleNamespace(market_cap=300_000_000_000.0, price_change_24h=4.0),
            [300_000_000_000.0, 900_000_000_000.0],
            [btc_coin, alt_coin],
            list(coin_metrics.values()),
        ]
    )
    leadership_narratives = await _build_sector_narratives_async(leadership_session)
    assert leadership_narratives[0].rotation_state == "sector_leadership_change"

    empty_bucket_session = _NarrativeSession(
        [
            [metric],
            SimpleNamespace(market_cap=300_000_000_000.0, price_change_24h=4.0),
            [300_000_000_000.0, 900_000_000_000.0],
            [],
        ]
    )
    empty_bucket_narratives = await _build_sector_narratives_async(empty_bucket_session)
    assert empty_bucket_narratives[0].capital_wave is None
