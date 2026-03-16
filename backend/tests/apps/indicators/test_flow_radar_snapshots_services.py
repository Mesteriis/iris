import json
from collections.abc import Mapping
from datetime import timedelta
from types import SimpleNamespace

import pytest
import src.apps.indicators.query_services as indicator_query_module
from sqlalchemy import select
from src.apps.indicators.models import CoinMetrics, FeatureSnapshot
from src.apps.indicators.query_services import IndicatorQueryService
from src.apps.indicators.read_models import market_radar_coin_read_model_from_mapping
from src.apps.indicators.services import (
    AnalysisSchedulerService,
    FeatureSnapshotService,
)
from src.core.db.uow import SessionUnitOfWork


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
async def test_indicator_query_services_cover_flow_radar_and_snapshots(
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

    serialized = market_radar_coin_read_model_from_mapping(
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
    )
    assert serialized.coin_id == 77
    assert serialized.activity_score is None

    async with SessionUnitOfWork(async_db_session) as uow:
        skipped = await FeatureSnapshotService(uow).capture_snapshot(
            coin_id=999999,
            timeframe=15,
            timestamp=timestamp,
            price_current=100.0,
            rsi_14=55.0,
            macd=1.2,
        )
    assert skipped.reason == "coin_not_found"

    async with SessionUnitOfWork(async_db_session) as uow:
        captured = await FeatureSnapshotService(uow).capture_snapshot(
            coin_id=int(btc.id),
            timeframe=15,
            timestamp=timestamp,
            price_current=112000.0,
            rsi_14=62.0,
            macd=1.4,
        )
    assert captured.status == "ok"
    assert captured.market_regime == "bull_trend"
    assert captured.cycle_phase == "markup"
    assert captured.pattern_density == 1
    assert captured.cluster_score == 998.0

    async with SessionUnitOfWork(async_db_session) as uow:
        updated = await FeatureSnapshotService(uow).capture_snapshot(
            coin_id=int(btc.id),
            timeframe=15,
            timestamp=timestamp,
            price_current=113500.0,
            rsi_14=63.0,
            macd=1.6,
        )
        await uow.commit()
    assert updated.price_current == 113500.0
    snapshot_row = await async_db_session.get(FeatureSnapshot, (int(btc.id), 15, timestamp))
    assert snapshot_row is not None
    assert float(snapshot_row.price_current) == 113500.0

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    metrics = await query_service.list_coin_metrics()
    evt_symbols = {row.symbol for row in metrics if row.symbol.endswith("_EVT")}
    assert {"BTCUSD_EVT", "ETHUSD_EVT", "SOLUSD_EVT"} <= evt_symbols

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    radar = await query_service.get_market_radar(limit=10)
    assert any(row.symbol == "BTCUSD_EVT" for row in radar.hot_coins)

    async_client = _AsyncRedisClient(messages)
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: async_client)
    flow = await query_service.get_market_flow(limit=10, timeframe=60)
    assert flow.leaders[0].symbol == "BTCUSD_EVT"
    assert flow.relations[0].follower_symbol == "ETHUSD_EVT"
    assert any(row.sector == "store_of_value" for row in flow.sectors)


@pytest.mark.asyncio
async def test_analysis_scheduler_service_honors_due_window_and_updates_state(async_db_session, seeded_api_state) -> None:
    btc = seeded_api_state["btc"]
    base_timestamp = seeded_api_state["signal_timestamp"]
    metrics = await async_db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(btc.id)).limit(1))
    assert metrics is not None
    assert metrics.last_analysis_at == base_timestamp

    async with SessionUnitOfWork(async_db_session) as uow:
        skipped = await AnalysisSchedulerService(uow).evaluate_indicator_update(
            coin_id=int(btc.id),
            timeframe=15,
            timestamp=base_timestamp + timedelta(minutes=10),
            activity_bucket_hint=None,
        )
    assert skipped.should_publish is False
    assert skipped.state_updated is False

    metrics_after_skip = await async_db_session.scalar(
        select(CoinMetrics).where(CoinMetrics.coin_id == int(btc.id)).limit(1)
    )
    assert metrics_after_skip is not None
    assert metrics_after_skip.last_analysis_at == base_timestamp

    due_timestamp = base_timestamp + timedelta(minutes=20)
    async with SessionUnitOfWork(async_db_session) as uow:
        ready = await AnalysisSchedulerService(uow).evaluate_indicator_update(
            coin_id=int(btc.id),
            timeframe=15,
            timestamp=due_timestamp,
            activity_bucket_hint=None,
        )
        if ready.state_updated:
            await uow.commit()
    assert ready.should_publish is True
    assert ready.state_updated is True
    assert ready.activity_bucket == "HOT"

    metrics_after_commit = await async_db_session.scalar(
        select(CoinMetrics).where(CoinMetrics.coin_id == int(btc.id)).limit(1)
    )
    assert metrics_after_commit is not None
    assert metrics_after_commit.last_analysis_at == due_timestamp

    async with SessionUnitOfWork(async_db_session) as uow:
        unknown_coin = await AnalysisSchedulerService(uow).evaluate_indicator_update(
            coin_id=999999,
            timeframe=15,
            timestamp=due_timestamp,
            activity_bucket_hint="WARM",
        )
    assert unknown_coin.should_publish is True
    assert unknown_coin.state_updated is False
    assert unknown_coin.activity_bucket == "WARM"
