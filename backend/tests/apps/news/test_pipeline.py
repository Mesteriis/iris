import multiprocessing
from datetime import UTC, datetime

import pytest
from iris.apps.news.models import NewsItem, NewsSource
from iris.apps.news.query_services import NewsQueryService
from iris.runtime.control_plane.worker import create_topology_dispatcher_consumer
from iris.runtime.streams.publisher import flush_publisher, publish_event
from iris.runtime.streams.runner import run_worker_loop
from redis import Redis


def _run_topology_dispatcher() -> None:
    worker = create_topology_dispatcher_consumer()
    try:
        worker.run()
    finally:
        worker.close()


@pytest.mark.asyncio
async def test_news_pipeline_normalizes_and_creates_symbol_links(
    async_db_session,
    seeded_market,
    settings,
    wait_until,
) -> None:
    del seeded_market
    source = NewsSource(
        plugin_name="x",
        display_name="Macro Tape",
        enabled=True,
        auth_mode="bearer_or_user_token",
        credentials_json={"bearer_token": "token"},
        settings_json={"user_id": "42"},
        cursor_json={},
    )
    async_db_session.add(source)
    await async_db_session.commit()
    await async_db_session.refresh(source)

    item = NewsItem(
        source_id=int(source.id),
        plugin_name="x",
        external_id="tweet-42",
        published_at=datetime(2026, 3, 12, 15, 0, tzinfo=UTC),
        author_handle="macrodesk",
        channel_name="Macro Tape",
        content_text="Watching $BTC and $ETH breakout after ETF approval",
        url="https://x.com/i/web/status/42",
        symbol_hints=["BTC", "ETH"],
        payload_json={"kind": "tweet"},
    )
    async_db_session.add(item)
    await async_db_session.commit()
    await async_db_session.refresh(item)
    item_id = int(item.id)
    source_id = int(source.id)
    published_at = item.published_at

    ctx = multiprocessing.get_context("spawn")
    dispatcher_worker = ctx.Process(
        target=_run_topology_dispatcher,
        daemon=True,
    )
    normalization_worker = ctx.Process(
        target=run_worker_loop,
        args=("news_normalization_workers",),
        daemon=True,
    )
    correlation_worker = ctx.Process(
        target=run_worker_loop,
        args=("news_correlation_workers",),
        daemon=True,
    )
    dispatcher_worker.start()
    normalization_worker.start()
    correlation_worker.start()
    try:
        publish_event(
            "news_item_ingested",
            {
                "coin_id": 0,
                "timeframe": 0,
                "timestamp": published_at,
                "item_id": item_id,
                "source_id": source_id,
                "plugin_name": "x",
            },
        )
        assert flush_publisher(timeout=5.0)

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await wait_until(
                lambda: {"news_item_normalized", "news_symbol_correlation_updated"}
                <= {fields["event_type"] for _, fields in client.xrange(settings.event_stream_name, "-", "+")},
                timeout=20.0,
                interval=0.2,
            )
            await async_db_session.rollback()
            current_item = next(
                item
                for item in await NewsQueryService(async_db_session).list_items(limit=10)
                if item.id == item_id
            )
            assert current_item.normalization_status == "normalized"
            assert sorted(current_item.normalized_payload_json["detected_symbols"]) == ["BTC", "ETH"]
            assert float(current_item.relevance_score or 0.0) > 0.0

            linked_symbols = sorted(link.coin_symbol for link in current_item.links)
            assert len(linked_symbols) == 2
            assert any(symbol.startswith("BTCUSD") for symbol in linked_symbols)
            assert any(symbol.startswith("ETHUSD") for symbol in linked_symbols)

            messages = client.xrange(settings.event_stream_name, "-", "+")
            event_types = [fields["event_type"] for _, fields in messages]
            assert "news_item_ingested" in event_types
            assert "news_item_normalized" in event_types
            assert "news_symbol_correlation_updated" in event_types
        finally:
            client.close()
    finally:
        dispatcher_worker.terminate()
        normalization_worker.terminate()
        correlation_worker.terminate()
        dispatcher_worker.join(timeout=2.0)
        normalization_worker.join(timeout=2.0)
        correlation_worker.join(timeout=2.0)
