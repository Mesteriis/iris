from __future__ import annotations

import json
import multiprocessing
from datetime import UTC, datetime

import pytest
from redis import Redis
from sqlalchemy import func, select
from src.apps.news.models import NewsItem, NewsItemLink, NewsSource
from src.apps.signals.models import MarketDecision
from src.apps.signals.services import SignalFusionService
from src.core.db.uow import SessionUnitOfWork
from src.runtime.control_plane.worker import create_topology_dispatcher_consumer
from src.runtime.streams.publisher import flush_publisher, publish_event
from src.runtime.streams.runner import run_worker_loop

from tests.fusion_support import create_test_coin, insert_signals, replace_pattern_statistics, upsert_coin_metrics


def _run_dispatcher_loop() -> None:
    consumer = create_topology_dispatcher_consumer()
    try:
        consumer.run()
    finally:
        consumer.close()


def _start_fusion_pipeline_processes() -> tuple[multiprocessing.Process, multiprocessing.Process]:
    ctx = multiprocessing.get_context("spawn")
    dispatcher = ctx.Process(target=_run_dispatcher_loop, daemon=True)
    worker = ctx.Process(
        target=run_worker_loop,
        args=("signal_fusion_workers",),
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


async def _evaluate_market_decision(async_db_session, **kwargs):
    async with SessionUnitOfWork(async_db_session) as uow:
        result = await SignalFusionService(uow).evaluate_market_decision(**kwargs)
        await uow.commit()
        return result


@pytest.mark.asyncio
async def test_signal_fusion_aggregates_bullish_stack_into_buy(async_db_session, db_session) -> None:
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    coin_id = int(coin.id)
    timestamp = datetime(2026, 3, 11, 13, 45, tzinfo=UTC)
    upsert_coin_metrics(db_session, coin_id=coin_id, regime="bull_trend")
    replace_pattern_statistics(
        db_session,
        timeframe=15,
        rows=[
            ("bull_flag", "all", 0.72, 60),
            ("breakout_retest", "all", 0.69, 55),
            ("macd_cross", "all", 0.66, 80),
        ],
    )
    insert_signals(
        db_session,
        coin_id=coin_id,
        timeframe=15,
        candle_timestamp=timestamp,
        items=[
            ("pattern_bull_flag", 0.82),
            ("pattern_breakout_retest", 0.77),
            ("pattern_macd_cross", 0.74),
        ],
    )

    result = await _evaluate_market_decision(
        async_db_session,
        coin_id=coin_id,
        timeframe=15,
        trigger_timestamp=timestamp,
        emit_event=False,
    )

    assert result.status == "ok"
    assert result.decision == "BUY"
    assert float(result.confidence or 0.0) >= 0.45
    db_session.expire_all()
    latest = db_session.scalar(
        select(MarketDecision)
        .where(MarketDecision.coin_id == coin_id, MarketDecision.timeframe == 15)
        .order_by(MarketDecision.created_at.desc(), MarketDecision.id.desc())
        .limit(1)
    )
    assert latest is not None
    assert latest.decision == "BUY"
    assert int(latest.signal_count) == 3


@pytest.mark.asyncio
async def test_signal_fusion_uses_recent_news_context(async_db_session, db_session) -> None:
    coin = create_test_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test")
    coin_id = int(coin.id)
    signal_timestamp = datetime(2026, 3, 11, 13, 45, tzinfo=UTC)
    news_timestamp = datetime(2026, 3, 11, 14, 0, tzinfo=UTC)
    upsert_coin_metrics(db_session, coin_id=coin_id, regime="bull_trend")
    replace_pattern_statistics(
        db_session,
        timeframe=15,
        rows=[("bull_flag", "all", 0.68, 40)],
    )
    insert_signals(
        db_session,
        coin_id=coin_id,
        timeframe=15,
        candle_timestamp=signal_timestamp,
        items=[("pattern_bull_flag", 0.74)],
    )
    source = NewsSource(
        plugin_name="x",
        display_name="Macro Tape",
        enabled=True,
        auth_mode="bearer_or_user_token",
        credentials_json={"bearer_token": "token"},
        settings_json={"user_id": "42"},
        cursor_json={},
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    item = NewsItem(
        source_id=int(source.id),
        plugin_name="x",
        external_id="tweet-eth-1",
        published_at=news_timestamp,
        author_handle="macrodesk",
        channel_name="Macro Tape",
        content_text="Strong $ETH breakout after ETF approval",
        url="https://x.com/i/web/status/eth1",
        symbol_hints=["ETH"],
        payload_json={"kind": "tweet"},
        normalization_status="normalized",
        normalized_payload_json={"detected_symbols": ["ETH"], "topics": ["regulation"]},
        normalized_at=news_timestamp,
        sentiment_score=0.82,
        relevance_score=0.91,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    db_session.add(
        NewsItemLink(
            news_item_id=int(item.id),
            coin_id=coin_id,
            coin_symbol=coin.symbol,
            matched_symbol="ETH",
            link_type="cashtag",
            confidence=0.93,
        )
    )
    db_session.commit()

    result = await _evaluate_market_decision(
        async_db_session,
        coin_id=coin_id,
        timeframe=15,
        news_reference_timestamp=news_timestamp,
        emit_event=False,
    )

    assert result.status == "ok"
    assert result.decision == "BUY"
    assert result.news_item_count == 1
    assert result.news_bullish_score > 0.0
    assert result.news_bearish_score == 0.0


@pytest.mark.asyncio
async def test_signal_fusion_worker_publishes_decision_event(async_db_session, db_session, settings, wait_until):
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    coin_id = int(coin.id)
    timestamp = datetime(2026, 3, 11, 13, 45, tzinfo=UTC)
    upsert_coin_metrics(db_session, coin_id=coin_id, regime="bull_trend")
    replace_pattern_statistics(
        db_session,
        timeframe=15,
        rows=[
            ("bull_flag", "all", 0.71, 50),
            ("breakout_retest", "all", 0.67, 50),
        ],
    )
    insert_signals(
        db_session,
        coin_id=coin_id,
        timeframe=15,
        candle_timestamp=timestamp,
        items=[
            ("pattern_bull_flag", 0.81),
            ("pattern_breakout_retest", 0.79),
        ],
    )

    dispatcher, worker = _start_fusion_pipeline_processes()
    try:
        publish_event(
            "signal_created",
            {
                "coin_id": coin_id,
                "timeframe": 15,
                "timestamp": timestamp,
                "signal_type": "pattern_bull_flag",
            },
        )
        assert flush_publisher(timeout=5.0)

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            def _decision_event_ready() -> bool:
                for _, fields in client.xrange(settings.event_stream_name, "-", "+"):
                    if fields.get("event_type") != "decision_generated":
                        continue
                    payload = json.loads(fields.get("payload", "{}"))
                    if payload.get("source") == "signal_fusion":
                        return True
                return False

            await wait_until(_decision_event_ready, timeout=10.0, interval=0.2)
        finally:
            client.close()

        await async_db_session.rollback()
        async_db_session.expire_all()
        count = int(
            (
                await async_db_session.scalar(
                    select(func.count())
                    .select_from(MarketDecision)
                    .where(MarketDecision.coin_id == coin_id, MarketDecision.timeframe == 15)
                )
            )
            or 0
        )
        assert count > 0
    finally:
        _stop_processes(dispatcher, worker)


@pytest.mark.asyncio
async def test_signal_fusion_worker_reacts_to_news_symbol_correlation_event(async_db_session, db_session, settings, wait_until):
    coin = create_test_coin(db_session, symbol="SOLUSD_EVT", name="Solana Event Test")
    coin_id = int(coin.id)
    signal_timestamp = datetime(2026, 3, 11, 13, 45, tzinfo=UTC)
    news_timestamp = datetime(2026, 3, 11, 14, 5, tzinfo=UTC)
    upsert_coin_metrics(db_session, coin_id=coin_id, regime="bull_trend")
    replace_pattern_statistics(
        db_session,
        timeframe=15,
        rows=[("bull_flag", "all", 0.7, 50)],
    )
    insert_signals(
        db_session,
        coin_id=coin_id,
        timeframe=15,
        candle_timestamp=signal_timestamp,
        items=[("pattern_bull_flag", 0.76)],
    )
    source = NewsSource(
        plugin_name="x",
        display_name="Macro Tape",
        enabled=True,
        auth_mode="bearer_or_user_token",
        credentials_json={"bearer_token": "token"},
        settings_json={"user_id": "42"},
        cursor_json={},
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    item = NewsItem(
        source_id=int(source.id),
        plugin_name="x",
        external_id="tweet-sol-1",
        published_at=news_timestamp,
        author_handle="macrodesk",
        channel_name="Macro Tape",
        content_text="Bullish $SOL launch catalyst",
        url="https://x.com/i/web/status/sol1",
        symbol_hints=["SOL"],
        payload_json={"kind": "tweet"},
        normalization_status="normalized",
        normalized_payload_json={"detected_symbols": ["SOL"], "topics": ["listing"]},
        normalized_at=news_timestamp,
        sentiment_score=0.74,
        relevance_score=0.88,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    db_session.add(
        NewsItemLink(
            news_item_id=int(item.id),
            coin_id=coin_id,
            coin_symbol=coin.symbol,
            matched_symbol="SOL",
            link_type="cashtag",
            confidence=0.9,
        )
    )
    db_session.commit()

    dispatcher, worker = _start_fusion_pipeline_processes()
    try:
        publish_event(
            "news_symbol_correlation_updated",
            {
                "coin_id": coin_id,
                "timeframe": 0,
                "timestamp": news_timestamp,
                "item_id": int(item.id),
                "source_id": int(source.id),
                "plugin_name": "x",
                "coin_symbol": coin.symbol,
                "matched_symbol": "SOL",
                "link_type": "cashtag",
                "confidence": 0.9,
                "relevance_score": 0.88,
                "sentiment_score": 0.74,
            },
        )
        assert flush_publisher(timeout=5.0)

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            def _decision_event_ready() -> bool:
                for _, fields in client.xrange(settings.event_stream_name, "-", "+"):
                    if fields.get("event_type") != "decision_generated":
                        continue
                    payload = json.loads(fields.get("payload", "{}"))
                    if payload.get("source") == "signal_fusion" and payload.get("news_item_count", 0) > 0:
                        return True
                return False

            await wait_until(_decision_event_ready, timeout=10.0, interval=0.2)
        finally:
            client.close()

        await async_db_session.rollback()
        async_db_session.expire_all()
        latest = await async_db_session.scalar(
            select(MarketDecision)
            .where(MarketDecision.coin_id == coin_id, MarketDecision.timeframe == 15)
            .order_by(MarketDecision.created_at.desc(), MarketDecision.id.desc())
            .limit(1)
        )
        assert latest is not None
        assert latest.decision == "BUY"
    finally:
        _stop_processes(dispatcher, worker)
