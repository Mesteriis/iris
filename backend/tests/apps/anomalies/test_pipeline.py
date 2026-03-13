from __future__ import annotations

import multiprocessing
from datetime import timedelta

import pytest
from sqlalchemy import select
from src.apps.anomalies.models import MarketAnomaly
from src.apps.anomalies.tasks.anomaly_enrichment_tasks import anomaly_enrichment_job
from src.apps.market_data.repos import fetch_candle_points, upsert_base_candles
from src.apps.market_data.service_layer import get_coin_by_symbol
from src.apps.market_data.sources.base import MarketBar
from src.apps.portfolio.models import PortfolioPosition
from src.runtime.control_plane.worker import create_topology_dispatcher_consumer
from src.runtime.streams.publisher import flush_publisher, publish_event
from src.runtime.streams.runner import run_worker_loop


def _append_shock_bar(db, *, symbol: str, close_multiplier: float, volume_multiplier: float, source: str) -> tuple[int, object]:
    coin = get_coin_by_symbol(db, symbol)
    assert coin is not None
    candles = fetch_candle_points(db, int(coin.id), 15, 2)
    latest = candles[-1]
    next_timestamp = latest.timestamp + timedelta(minutes=15)
    bar = MarketBar(
        timestamp=next_timestamp,
        open=float(latest.close),
        high=float(latest.close) * max(close_multiplier, 1.0) * 1.02,
        low=float(latest.close) * 0.995,
        close=float(latest.close) * close_multiplier,
        volume=(float(latest.volume or 1000.0) * volume_multiplier),
        source=source,
    )
    upsert_base_candles(db, coin, "15m", [bar])
    return int(coin.id), next_timestamp


def _run_dispatcher_loop() -> None:
    consumer = create_topology_dispatcher_consumer()
    try:
        consumer.run()
    finally:
        consumer.close()


def _start_anomaly_pipeline_processes() -> tuple[multiprocessing.Process, multiprocessing.Process]:
    ctx = multiprocessing.get_context("spawn")
    dispatcher = ctx.Process(target=_run_dispatcher_loop, daemon=True)
    worker = ctx.Process(
        target=run_worker_loop,
        args=("anomaly_workers",),
        daemon=True,
    )
    dispatcher.start()
    worker.start()
    return dispatcher, worker


def _stop_processes(*processes: multiprocessing.Process) -> None:
    for process in processes:
        process.terminate()
    for process in processes:
        process.join(timeout=2.0)


@pytest.mark.asyncio
async def test_candle_closed_pipeline_persists_and_publishes_anomaly(
    db_session,
    seeded_market,
    settings,
    wait_until,
) -> None:
    del seeded_market
    eth_coin_id, event_timestamp = _append_shock_bar(
        db_session,
        symbol="ETHUSD_EVT",
        close_multiplier=1.14,
        volume_multiplier=7.0,
        source="anomaly_test",
    )
    _append_shock_bar(
        db_session,
        symbol="BTCUSD_EVT",
        close_multiplier=1.004,
        volume_multiplier=1.2,
        source="anomaly_test",
    )

    dispatcher, worker = _start_anomaly_pipeline_processes()
    try:
        publish_event(
            "candle_closed",
            {
                "coin_id": eth_coin_id,
                "timeframe": 15,
                "timestamp": event_timestamp,
                "source": "anomaly_test",
            },
        )
        assert flush_publisher(timeout=5.0)

        def _anomaly_published() -> bool:
            messages = redis_client.xrange(settings.event_stream_name, "-", "+")
            return any(fields["event_type"] == "anomaly_detected" for _, fields in messages)

        from redis import Redis

        redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await wait_until(_anomaly_published, timeout=20.0, interval=0.2)
            db_session.expire_all()
            anomaly = db_session.scalar(
                select(MarketAnomaly)
                .where(MarketAnomaly.coin_id == eth_coin_id, MarketAnomaly.timeframe == 15)
                .order_by(MarketAnomaly.detected_at.desc())
                .limit(1)
            )
            assert anomaly is not None
            assert int(anomaly.coin_id) == eth_coin_id
            assert anomaly.status == "new"
            assert anomaly.anomaly_type in {
                "price_spike",
                "volume_spike",
                "volatility_regime_break",
                "relative_divergence",
                "failed_breakout",
                "compression_expansion",
                "price_volume_divergence",
                "correlation_breakdown",
            }

            stream_messages = redis_client.xrange(settings.event_stream_name, "-", "+")
            anomaly_messages = [fields for _, fields in stream_messages if fields["event_type"] == "anomaly_detected"]
            assert anomaly_messages
            assert any('"severity"' in item["payload"] for item in anomaly_messages)
        finally:
            redis_client.close()
    finally:
        _stop_processes(dispatcher, worker)


@pytest.mark.asyncio
async def test_anomaly_enrichment_task_updates_status_and_context(
    db_session,
    seeded_market,
    settings,
    wait_until,
) -> None:
    del seeded_market
    eth_coin_id, event_timestamp = _append_shock_bar(
        db_session,
        symbol="ETHUSD_EVT",
        close_multiplier=1.12,
        volume_multiplier=6.0,
        source="anomaly_enrichment_test",
    )
    _append_shock_bar(
        db_session,
        symbol="BTCUSD_EVT",
        close_multiplier=1.003,
        volume_multiplier=1.1,
        source="anomaly_enrichment_test",
    )
    db_session.add(
        PortfolioPosition(
            coin_id=eth_coin_id,
            timeframe=15,
            entry_price=100.0,
            position_size=1.0,
            position_value=100.0,
            status="open",
        )
    )
    db_session.commit()

    dispatcher, worker = _start_anomaly_pipeline_processes()
    try:
        publish_event(
            "candle_closed",
            {
                "coin_id": eth_coin_id,
                "timeframe": 15,
                "timestamp": event_timestamp,
                "source": "anomaly_enrichment_test",
            },
        )
        assert flush_publisher(timeout=5.0)
        from redis import Redis

        redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await wait_until(
                lambda: any(
                    fields["event_type"] == "anomaly_detected"
                    and int(fields.get("coin_id") or 0) == eth_coin_id
                    for _, fields in redis_client.xrange(settings.event_stream_name, "-", "+")
                ),
                timeout=20.0,
                interval=0.2,
            )
        finally:
            redis_client.close()
    finally:
        _stop_processes(dispatcher, worker)

    db_session.expire_all()
    anomaly = db_session.scalar(
        select(MarketAnomaly)
        .where(MarketAnomaly.coin_id == eth_coin_id, MarketAnomaly.timeframe == 15)
        .order_by(MarketAnomaly.detected_at.desc())
        .limit(1)
    )
    assert anomaly is not None
    anomaly_id = int(anomaly.id)

    result = await anomaly_enrichment_job(anomaly_id)
    assert result["status"] == "ok"

    db_session.expire_all()
    anomaly = db_session.get(MarketAnomaly, anomaly_id)
    assert anomaly is not None
    assert anomaly.status == "active"
    assert anomaly.payload_json["context"]["portfolio_relevant"] is True
    assert anomaly.payload_json["explainability"]["portfolio_impact"] == "portfolio exposure present"
