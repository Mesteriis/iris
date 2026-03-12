from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import src.apps.indicators.market_flow as market_flow_module
import src.apps.indicators.market_radar as market_radar_module
import src.apps.indicators.services as indicator_services_module
from src.apps.indicators.market_flow import _recent_market_leaders, _recent_sector_rotations, get_market_flow
from src.apps.indicators.market_radar import _metric_rows, _recent_regime_changes, get_market_radar
from src.apps.indicators.models import FeatureSnapshot
from src.apps.indicators.services import (
    _recent_market_leaders_async,
    _recent_regime_changes_async,
    _recent_sector_rotations_async,
    _serialize_metric_rows,
    get_market_flow_async,
    get_market_radar_async,
    list_coin_metrics_async,
)
from src.apps.indicators.snapshots import capture_feature_snapshot


class _SyncRedisClient:
    def __init__(self, messages: list[tuple[str, dict[str, str]]]) -> None:
        self._messages = messages
        self.closed = False

    def xrevrange(self, _stream: str, _max: str, _min: str, *, count: int):
        return self._messages[:count]

    def close(self) -> None:
        self.closed = True


class _AsyncRedisClient:
    def __init__(self, messages: list[tuple[str, dict[str, str]]]) -> None:
        self._messages = messages
        self.closed = False

    async def xrevrange(self, _stream: str, _max: str, _min: str, *, count: int):
        return self._messages[:count]

    async def aclose(self) -> None:
        self.closed = True


def _stream_messages(seeded_api_state) -> list[tuple[str, dict[str, str]]]:
    timestamp = seeded_api_state["signal_timestamp"]
    btc = seeded_api_state["btc"]
    return [
        (
            "5-0",
            {
                "event_type": "market_regime_changed",
                "coin_id": "999999",
                "timeframe": "240",
                "timestamp": timestamp.isoformat(),
                "payload": "{}",
            },
        ),
        (
            "4-0",
            {
                "event_type": "market_regime_changed",
                "coin_id": str(btc.id),
                "timeframe": "60",
                "timestamp": timestamp.isoformat(),
                "payload": json.dumps({"regime": "bull_trend", "confidence": 0.83}),
            },
        ),
        (
            "3-0",
            {
                "event_type": "market_regime_changed",
                "coin_id": str(btc.id),
                "timeframe": "60",
                "timestamp": timestamp.isoformat(),
                "payload": json.dumps({"regime": "bull_trend", "confidence": 0.83}),
            },
        ),
        (
            "2-0",
            {
                "event_type": "market_leader_detected",
                "coin_id": str(btc.id),
                "timeframe": "60",
                "timestamp": timestamp.isoformat(),
                "payload": json.dumps({"confidence": 0.88}),
            },
        ),
        (
            "1-1",
            {
                "event_type": "market_leader_detected",
                "coin_id": str(btc.id),
                "timeframe": "60",
                "timestamp": timestamp.isoformat(),
                "payload": json.dumps({"confidence": 0.77}),
            },
        ),
        (
            "1-0",
            {
                "event_type": "market_leader_detected",
                "coin_id": "999999",
                "timeframe": "60",
                "timestamp": timestamp.isoformat(),
                "payload": json.dumps({"confidence": 0.55}),
            },
        ),
        (
            "0-1",
            {
                "event_type": "sector_rotation_detected",
                "coin_id": str(btc.id),
                "timeframe": "60",
                "timestamp": timestamp.isoformat(),
                "payload": json.dumps({"source_sector": "store_of_value", "target_sector": "smart_contract"}),
            },
        ),
        (
            "0-2",
            {
                "event_type": "sector_rotation_detected",
                "coin_id": str(btc.id),
                "timeframe": "60",
                "timestamp": timestamp.isoformat(),
                "payload": json.dumps({"source_sector": "store_of_value", "target_sector": "smart_contract"}),
            },
        ),
        (
            "0-0",
            {
                "event_type": "sector_rotation_detected",
                "coin_id": str(btc.id),
                "timeframe": "60",
                "timestamp": timestamp.isoformat(),
                "payload": json.dumps({"source_sector": "", "target_sector": "smart_contract"}),
            },
        ),
    ]


def test_indicator_sync_flow_radar_and_snapshot_paths(db_session, seeded_api_state, monkeypatch) -> None:
    btc = seeded_api_state["btc"]
    timestamp = seeded_api_state["signal_timestamp"]
    messages = _stream_messages(seeded_api_state)
    sync_client = _SyncRedisClient(messages)

    monkeypatch.setattr(market_flow_module.Redis, "from_url", staticmethod(lambda *args, **kwargs: sync_client))
    monkeypatch.setattr(market_radar_module.Redis, "from_url", staticmethod(lambda *args, **kwargs: sync_client))

    leaders = _recent_market_leaders(db_session, limit=10)
    assert len(leaders) == 1
    assert leaders[0].symbol == "BTCUSD_EVT"
    assert leaders[0].regime == "bull_trend"
    assert sync_client.closed is True
    assert len(_recent_market_leaders(db_session, limit=1)) == 1

    rotations = _recent_sector_rotations(limit=10)
    assert len(rotations) == 1
    assert rotations[0].source_sector == "store_of_value"
    assert len(_recent_sector_rotations(limit=1)) == 1

    flow = get_market_flow(db_session, limit=10, timeframe=60)
    assert flow.leaders[0].symbol == "BTCUSD_EVT"
    assert flow.relations[0].leader_symbol == "BTCUSD_EVT"
    assert flow.sectors[0].sector == "store_of_value"
    assert flow.rotations[0].target_sector == "smart_contract"

    regime_changes = _recent_regime_changes(db_session, limit=10)
    assert len(regime_changes) == 2
    assert regime_changes[0].regime == "unknown"
    assert regime_changes[0].symbol == "UNKNOWN"
    assert any(change.symbol == "BTCUSD_EVT" and change.regime == "bull_trend" for change in regime_changes)
    monkeypatch.setattr(market_radar_module.Redis, "from_url", staticmethod(lambda *args, **kwargs: sync_client))
    assert len(_recent_regime_changes(db_session, limit=1)) == 1
    empty_client = _SyncRedisClient([("0-0", {"event_type": "ignored"})])
    monkeypatch.setattr(market_radar_module.Redis, "from_url", staticmethod(lambda *args, **kwargs: empty_client))
    assert _recent_regime_changes(db_session, limit=1) == []
    monkeypatch.setattr(market_radar_module.Redis, "from_url", staticmethod(lambda *args, **kwargs: sync_client))

    radar = get_market_radar(db_session, limit=10)
    assert any(row.symbol == "BTCUSD_EVT" for row in radar.hot_coins)
    assert any(row.symbol == "BTCUSD_EVT" for row in radar.emerging_coins)
    assert any(change.symbol == "BTCUSD_EVT" for change in radar.regime_changes)
    assert radar.volatility_spikes

    serialized = _metric_rows(
        db_session,
        stmt=select(
            market_radar_module.Coin.id.label("coin_id"),
            market_radar_module.Coin.symbol,
            market_radar_module.Coin.name,
            market_radar_module.CoinMetrics.activity_score,
            market_radar_module.CoinMetrics.activity_bucket,
            market_radar_module.CoinMetrics.analysis_priority,
            market_radar_module.CoinMetrics.price_change_24h,
            market_radar_module.CoinMetrics.price_change_7d,
            market_radar_module.CoinMetrics.volatility,
            market_radar_module.CoinMetrics.market_regime,
            market_radar_module.CoinMetrics.updated_at,
            market_radar_module.CoinMetrics.last_analysis_at,
        )
        .join(market_radar_module.CoinMetrics, market_radar_module.CoinMetrics.coin_id == market_radar_module.Coin.id)
        .where(market_radar_module.Coin.symbol == "BTCUSD_EVT"),
    )
    assert serialized[0].symbol == "BTCUSD_EVT"

    skipped = capture_feature_snapshot(
        db_session,
        coin_id=999999,
        timeframe=15,
        timestamp=timestamp,
        price_current=100.0,
        rsi_14=55.0,
        macd=1.2,
        commit=False,
    )
    assert skipped["reason"] == "coin_not_found"

    captured = capture_feature_snapshot(
        db_session,
        coin_id=int(btc.id),
        timeframe=15,
        timestamp=timestamp,
        price_current=112000.0,
        rsi_14=62.0,
        macd=1.4,
        commit=False,
    )
    assert captured["status"] == "ok"
    assert captured["market_regime"] == "bull_trend"
    assert captured["cycle_phase"] == "markup"
    assert captured["pattern_density"] == 1
    assert captured["cluster_score"] == 998.0

    updated = capture_feature_snapshot(
        db_session,
        coin_id=int(btc.id),
        timeframe=15,
        timestamp=timestamp,
        price_current=113500.0,
        rsi_14=63.0,
        macd=1.6,
        commit=True,
    )
    assert updated["price_current"] == 113500.0
    snapshot_row = db_session.get(FeatureSnapshot, (int(btc.id), 15, timestamp))
    assert snapshot_row is not None
    assert float(snapshot_row.price_current) == 113500.0


@pytest.mark.asyncio
async def test_indicator_async_services_cover_flow_radar_metric_serialization(async_db_session, seeded_api_state, monkeypatch) -> None:
    messages = _stream_messages(seeded_api_state)
    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_services_module, "_stream_client", lambda: async_client)

    metrics = await list_coin_metrics_async(async_db_session)
    evt_symbols = {row["symbol"] for row in metrics if row["symbol"].endswith("_EVT")}
    assert {"BTCUSD_EVT", "ETHUSD_EVT", "SOLUSD_EVT"} <= evt_symbols

    serialized = _serialize_metric_rows(
        [
            SimpleNamespace(
                coin_id=77,
                symbol="NULL_EVT",
                name="Null Coin",
                activity_score=None,
                activity_bucket=None,
                analysis_priority=None,
                price_change_24h=None,
                price_change_7d=None,
                volatility=None,
                market_regime=None,
                updated_at=None,
                last_analysis_at=None,
            )
        ]
    )
    assert serialized[0].coin_id == 77
    assert serialized[0].activity_score is None

    regime_changes = await _recent_regime_changes_async(async_db_session, limit=10)
    assert len(regime_changes) == 2
    assert any(change.symbol == "UNKNOWN" for change in regime_changes)
    assert async_client.closed is True
    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_services_module, "_stream_client", lambda: async_client)
    assert len(await _recent_regime_changes_async(async_db_session, limit=1)) == 1

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_services_module, "_stream_client", lambda: async_client)
    leaders = await _recent_market_leaders_async(async_db_session, limit=10)
    assert len(leaders) == 1
    assert leaders[0].symbol == "BTCUSD_EVT"
    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_services_module, "_stream_client", lambda: async_client)
    assert len(await _recent_market_leaders_async(async_db_session, limit=1)) == 1

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_services_module, "_stream_client", lambda: async_client)
    rotations = await _recent_sector_rotations_async(limit=10)
    assert len(rotations) == 1
    assert rotations[0].target_sector == "smart_contract"
    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_services_module, "_stream_client", lambda: async_client)
    assert len(await _recent_sector_rotations_async(limit=1)) == 1

    async_client = _AsyncRedisClient([("0-0", {"event_type": "ignored"})])
    monkeypatch.setattr(indicator_services_module, "_stream_client", lambda: async_client)
    assert await _recent_regime_changes_async(async_db_session, limit=1) == []

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_services_module, "_stream_client", lambda: async_client)
    radar = await get_market_radar_async(async_db_session, limit=10)
    assert any(row.symbol == "BTCUSD_EVT" for row in radar.hot_coins)
    assert any(change.symbol == "BTCUSD_EVT" for change in radar.regime_changes)

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_services_module, "_stream_client", lambda: async_client)
    flow = await get_market_flow_async(async_db_session, limit=10, timeframe=60)
    assert flow.leaders[0].symbol == "BTCUSD_EVT"
    assert flow.relations[0].follower_symbol == "ETHUSD_EVT"
    assert any(row.sector == "store_of_value" for row in flow.sectors)
