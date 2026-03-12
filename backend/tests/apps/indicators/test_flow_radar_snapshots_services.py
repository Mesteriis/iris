from __future__ import annotations

import json
from collections.abc import Mapping
from types import SimpleNamespace

import pytest
import src.apps.indicators.query_services as indicator_query_module
from sqlalchemy import select
from src.apps.indicators.market_flow import _recent_market_leaders, _recent_sector_rotations, get_market_flow
from src.apps.indicators.market_radar import _metric_rows, _recent_regime_changes, get_market_radar
from src.apps.indicators.models import FeatureSnapshot
from src.apps.indicators.query_services import IndicatorQueryService
from src.apps.indicators.services import (
    capture_feature_snapshot,
    get_market_flow_async,
    get_market_radar_async,
    list_coin_metrics_async,
)


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


@pytest.mark.asyncio
async def test_indicator_query_services_and_async_wrappers_cover_flow_radar_and_snapshots(
    async_db_session,
    seeded_api_state,
    monkeypatch,
) -> None:
    btc = seeded_api_state["btc"]
    timestamp = seeded_api_state["signal_timestamp"]
    messages = _stream_messages(seeded_api_state)
    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)

    query_service = IndicatorQueryService(async_db_session)

    leaders = await query_service.list_recent_market_leaders(limit=10)
    assert len(leaders) == 1
    assert leaders[0].symbol == "BTCUSD_EVT"
    assert leaders[0].regime == "bull_trend"
    assert async_client.closed is True

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    rotations = await query_service.list_recent_sector_rotations(limit=10)
    assert len(rotations) == 1
    assert rotations[0].source_sector == "store_of_value"

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    flow = await query_service.get_market_flow(limit=10, timeframe=60)
    assert flow.leaders[0].symbol == "BTCUSD_EVT"
    assert flow.relations[0].leader_symbol == "BTCUSD_EVT"
    assert flow.sectors[0].sector == "store_of_value"
    assert flow.rotations[0].target_sector == "smart_contract"

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    regime_changes = await query_service.list_recent_regime_changes(limit=10)
    assert len(regime_changes) == 2
    assert regime_changes[0].regime == "unknown"
    assert regime_changes[0].symbol == "UNKNOWN"
    assert any(change.symbol == "BTCUSD_EVT" and change.regime == "bull_trend" for change in regime_changes)

    async_client = _AsyncRedisClient([("0-0", {"event_type": "ignored"})])
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    assert await query_service.list_recent_regime_changes(limit=1) == ()

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    radar = await query_service.get_market_radar(limit=10)
    assert any(row.symbol == "BTCUSD_EVT" for row in radar.hot_coins)
    assert any(row.symbol == "BTCUSD_EVT" for row in radar.emerging_coins)
    assert any(change.symbol == "BTCUSD_EVT" for change in radar.regime_changes)
    assert radar.volatility_spikes

    serialized = _metric_rows(
        [
            {
                "coin_id": 77,
                "symbol": "NULL_EVT",
                "name": "Null Coin",
                "activity_score": None,
                "activity_bucket": None,
                "analysis_priority": None,
                "price_change_24h": None,
                "price_change_7d": None,
                "volatility": None,
                "market_regime": None,
                "updated_at": None,
                "last_analysis_at": None,
            }
        ]
    )
    assert serialized[0].coin_id == 77
    assert serialized[0].activity_score is None

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    assert len(await _recent_market_leaders(async_db_session, limit=1)) == 1
    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    assert len(await _recent_sector_rotations(async_db_session, limit=1)) == 1
    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    assert len(await _recent_regime_changes(async_db_session, limit=1)) == 1
    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    assert (await get_market_radar(async_db_session, limit=10)).hot_coins
    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    assert (await get_market_flow(async_db_session, limit=10, timeframe=60)).leaders

    skipped = await capture_feature_snapshot(
        async_db_session,
        coin_id=999999,
        timeframe=15,
        timestamp=timestamp,
        price_current=100.0,
        rsi_14=55.0,
        macd=1.2,
        commit=False,
    )
    assert skipped.reason == "coin_not_found"

    captured = await capture_feature_snapshot(
        async_db_session,
        coin_id=int(btc.id),
        timeframe=15,
        timestamp=timestamp,
        price_current=112000.0,
        rsi_14=62.0,
        macd=1.4,
        commit=False,
    )
    assert captured.status == "ok"
    assert captured.market_regime == "bull_trend"
    assert captured.cycle_phase == "markup"
    assert captured.pattern_density == 1
    assert captured.cluster_score == 998.0

    updated = await capture_feature_snapshot(
        async_db_session,
        coin_id=int(btc.id),
        timeframe=15,
        timestamp=timestamp,
        price_current=113500.0,
        rsi_14=63.0,
        macd=1.6,
        commit=True,
    )
    assert updated.price_current == 113500.0
    snapshot_row = await async_db_session.get(FeatureSnapshot, (int(btc.id), 15, timestamp))
    assert snapshot_row is not None
    assert float(snapshot_row.price_current) == 113500.0

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    metrics = await list_coin_metrics_async(async_db_session)
    evt_symbols = {row.symbol for row in metrics if row.symbol.endswith("_EVT")}
    assert {"BTCUSD_EVT", "ETHUSD_EVT", "SOLUSD_EVT"} <= evt_symbols

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    radar = await get_market_radar_async(async_db_session, limit=10)
    assert any(row.symbol == "BTCUSD_EVT" for row in radar.hot_coins)

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    flow = await get_market_flow_async(async_db_session, limit=10, timeframe=60)
    assert flow.leaders[0].symbol == "BTCUSD_EVT"
    assert flow.relations[0].follower_symbol == "ETHUSD_EVT"
    assert any(row.sector == "store_of_value" for row in flow.sectors)
