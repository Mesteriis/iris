import multiprocessing

import pytest
from iris.apps.patterns.cache import read_cached_regime
from iris.apps.patterns.domain.regime import detect_market_regime
from iris.core.settings import get_settings
from iris.runtime.control_plane.worker import create_topology_dispatcher_consumer
from iris.runtime.streams.publisher import flush_publisher, publish_event
from iris.runtime.streams.runner import run_worker_loop
from redis import Redis


def _run_dispatcher_loop() -> None:
    consumer = create_topology_dispatcher_consumer()
    try:
        consumer.run()
    finally:
        consumer.close()


def test_market_regime_detection_rules() -> None:
    bull, bull_confidence = detect_market_regime(
        {
            "price_current": 120,
            "ema_50": 118,
            "ema_200": 100,
            "adx_14": 32,
            "price_change_7d": 9,
            "atr_14": 2.0,
            "prev_atr_14": 1.8,
            "bb_width": 0.06,
            "prev_bb_width": 0.05,
        }
    )
    bear, bear_confidence = detect_market_regime(
        {
            "price_current": 80,
            "ema_50": 82,
            "ema_200": 100,
            "adx_14": 30,
            "price_change_7d": -7,
            "atr_14": 2.2,
            "prev_atr_14": 2.0,
            "bb_width": 0.07,
            "prev_bb_width": 0.06,
        }
    )
    high_volatility, _ = detect_market_regime(
        {
            "price_current": 100,
            "ema_50": 100,
            "ema_200": 100,
            "adx_14": 18,
            "price_change_7d": 0,
            "atr_14": 4.0,
            "prev_atr_14": 3.2,
            "bb_width": 0.12,
            "prev_bb_width": 0.08,
        }
    )
    low_volatility, _ = detect_market_regime(
        {
            "price_current": 100,
            "ema_50": 100,
            "ema_200": 100,
            "adx_14": 14,
            "price_change_7d": 0,
            "atr_14": 1.0,
            "prev_atr_14": 1.02,
            "bb_width": 0.03,
            "prev_bb_width": 0.031,
        }
    )

    assert bull == "bull_trend"
    assert bull_confidence > 0.7
    assert bear == "bear_trend"
    assert bear_confidence > 0.7
    assert high_volatility == "high_volatility"
    assert low_volatility == "low_volatility"


@pytest.mark.asyncio
async def test_regime_worker_caches_and_emits_changes(seeded_market, wait_until) -> None:
    settings = get_settings()
    sample = seeded_market["ETHUSD_EVT"]
    ctx = multiprocessing.get_context("spawn")
    dispatcher = ctx.Process(
        target=_run_dispatcher_loop,
        daemon=True,
    )
    worker = ctx.Process(
        target=run_worker_loop,
        args=("regime_workers",),
        daemon=True,
    )
    dispatcher.start()
    worker.start()
    try:
        publish_event(
            "indicator_updated",
            {
                "coin_id": int(sample["coin_id"]),
                "timeframe": 15,
                "timestamp": sample["latest_timestamp"],
                "market_regime": "bull_trend",
                "regime_confidence": 0.87,
                "activity_bucket": "HOT",
                "activity_score": 81.0,
                "analysis_priority": 100,
            },
        )
        assert flush_publisher(timeout=5.0)
        await wait_until(
            lambda: read_cached_regime(coin_id=int(sample["coin_id"]), timeframe=15) is not None,
            timeout=8.0,
            interval=0.2,
        )

        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await wait_until(
                lambda: any(
                    fields.get("event_type") == "market_regime_changed"
                    for _, fields in redis.xrange(settings.event_stream_name, "-", "+")
                ),
                timeout=8.0,
                interval=0.2,
            )
        finally:
            redis.close()
    finally:
        dispatcher.terminate()
        worker.terminate()
        dispatcher.join(timeout=2.0)
        worker.join(timeout=2.0)
