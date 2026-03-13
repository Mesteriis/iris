from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src.apps.indicators.models import CoinMetrics
from src.apps.patterns.models import PatternFeature
from src.apps.patterns.selectors import (
    _cluster_membership_map,
    _signal_select,
    get_coin_regimes,
    get_pattern,
    list_coin_patterns,
    list_discovered_patterns,
    list_enriched_signals,
    list_market_cycles,
    list_pattern_features,
    list_patterns,
    list_sector_metrics,
    list_sectors,
    list_top_signals,
    update_pattern,
    update_pattern_feature,
)
from src.apps.signals.models import Signal
from tests.patterns_support import seed_pattern_api_state


def test_pattern_selectors_cover_listing_update_and_regime_branches(db_session, monkeypatch) -> None:
    seeded_api_state = seed_pattern_api_state(db_session)
    monkeypatch.setattr(
        "src.apps.patterns.selectors.build_sector_narratives",
        lambda _db: [
            SimpleNamespace(
                timeframe=60,
                top_sector="store_of_value",
                rotation_state="sector_leadership_change",
                btc_dominance=None,
                capital_wave="large_caps",
            )
        ],
    )
    patterns = list_patterns(db_session)
    assert {"bull_flag", "breakout_retest"} <= {row["slug"] for row in patterns}
    assert next(row for row in patterns if row["slug"] == "bull_flag")["statistics"]

    pattern = get_pattern(db_session, "bull_flag")
    assert pattern is not None
    assert pattern["statistics"][0]["market_regime"] == "all"
    assert get_pattern(db_session, "missing_pattern") is None

    features = list_pattern_features(db_session)
    assert {"market_regime_engine", "pattern_context_engine"} <= {row["feature_slug"] for row in features}
    assert update_pattern_feature(db_session, "missing_feature", enabled=False) is None
    assert update_pattern_feature(db_session, "pattern_context_engine", enabled=False)["enabled"] is False

    updated = update_pattern(db_session, "bull_flag", enabled=False, lifecycle_state=None, cpu_cost=0)
    assert updated is not None
    assert updated["enabled"] is False
    assert updated["lifecycle_state"] == "DISABLED"
    assert updated["cpu_cost"] == 1
    assert update_pattern(db_session, "missing_pattern", enabled=True, lifecycle_state=None, cpu_cost=None) is None
    with pytest.raises(ValueError):
        update_pattern(db_session, "breakout_retest", enabled=True, lifecycle_state="broken", cpu_cost=None)
    assert update_pattern(db_session, "breakout_retest", enabled=True, lifecycle_state="experimental", cpu_cost=4)["lifecycle_state"] == "EXPERIMENTAL"
    active_update = update_pattern(db_session, "breakout_retest", enabled=None, lifecycle_state="active", cpu_cost=None)
    assert active_update is not None
    assert active_update["lifecycle_state"] == "ACTIVE"

    discovered = list_discovered_patterns(db_session, timeframe=15, limit=0)
    assert discovered == [
        {
            "structure_hash": "cluster:bull_flag:15",
            "timeframe": 15,
            "sample_size": 18,
            "avg_return": 0.031,
            "avg_drawdown": -0.017,
            "confidence": 0.83,
        }
    ]
    assert list_discovered_patterns(db_session, limit=1)[0]["structure_hash"] == "cluster:bull_flag:15"

    enriched = list_enriched_signals(db_session, symbol="BTCUSD_EVT", timeframe=15, limit=10)
    assert [row["signal_type"] for row in enriched] == ["pattern_bull_flag", "pattern_cluster_breakout"]
    assert enriched[0]["cluster_membership"] == ["pattern_cluster_breakout"]
    assert enriched[0]["market_regime"] == "bull_trend"
    unfiltered_enriched = list_enriched_signals(db_session, limit=2)
    assert len(unfiltered_enriched) == 2
    raw_rows = (
        db_session.execute(
            _signal_select()
            .where(Signal.coin_id == seeded_api_state["btc"].id, Signal.timeframe == 15)
            .order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc())
        )
    ).all()
    assert _cluster_membership_map(db_session, []) == {}
    assert _cluster_membership_map(db_session, raw_rows)

    top_signals = list_top_signals(db_session, limit=1)
    assert len(top_signals) == 1
    assert top_signals[0]["signal_type"] == "pattern_bull_flag"

    coin_patterns = list_coin_patterns(db_session, "btcusd_evt", limit=10)
    assert [row["signal_type"] for row in coin_patterns] == ["pattern_bull_flag", "pattern_cluster_breakout"]

    regime = get_coin_regimes(db_session, "BTCUSD_EVT")
    assert regime is not None
    assert regime["canonical_regime"] == "bull_trend"
    assert regime["items"][0]["timeframe"] == 15
    assert get_coin_regimes(db_session, "missing_evt") is None

    market_regime_feature = db_session.get(PatternFeature, "market_regime_engine")
    assert market_regime_feature is not None
    market_regime_feature.enabled = False
    db_session.commit()
    disabled_regime = get_coin_regimes(db_session, "BTCUSD_EVT")
    assert disabled_regime == {"coin_id": seeded_api_state["btc"].id, "symbol": "BTCUSD_EVT", "canonical_regime": None, "items": []}

    market_regime_feature.enabled = True
    metrics = db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == seeded_api_state["btc"].id))
    assert metrics is not None
    metrics.market_regime_details = None
    db_session.commit()
    fallback_regime = get_coin_regimes(db_session, "BTCUSD_EVT")
    assert fallback_regime is not None
    assert fallback_regime["items"]

    sectors = list_sectors(db_session)
    assert {row["name"] for row in sectors} >= {"store_of_value", "smart_contract", "high_beta"}
    assert next(row for row in sectors if row["name"] == "store_of_value")["coin_count"] == 1

    sector_metrics = list_sector_metrics(db_session, timeframe=60)
    assert [row["name"] for row in sector_metrics["items"]] == ["store_of_value", "smart_contract"]
    assert sector_metrics["narratives"][0]["timeframe"] == 60
    sector_metrics_all = list_sector_metrics(db_session)
    assert sector_metrics_all["items"]

    cycles = list_market_cycles(db_session, symbol="BTCUSD_EVT", timeframe=15)
    assert len(cycles) == 1
    assert cycles[0]["cycle_phase"] == "markup"
    all_cycles = list_market_cycles(db_session)
    assert all_cycles
