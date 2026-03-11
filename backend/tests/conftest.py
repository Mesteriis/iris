from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from redis import Redis
from sqlalchemy import delete, select

os.environ.setdefault("EVENT_STREAM_NAME", "iris_events_test")

from app.core.config import get_settings

get_settings.cache_clear()

from app.db.session import SessionLocal
from app.events.publisher import flush_publisher, reset_event_publisher
from app.models.coin import Coin
from app.schemas.coin import CoinCreate
from app.services.history_loader import create_coin
from app.services.market_data import utc_now
from app.services.market_sources.base import MarketBar
from app.services.candles_service import upsert_base_candles

TEST_SYMBOLS = {
    "BTCUSD_EVT": ("BTCUSD", "Bitcoin Event Test"),
    "ETHUSD_EVT": ("ETHUSD", "Ethereum Event Test"),
    "SOLUSD_EVT": ("SOLUSD", "Solana Event Test"),
}


@pytest.fixture
def wait_until():
    async def _wait_until(predicate, *, timeout: float = 10.0, interval: float = 0.1):
        import asyncio

        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            result = predicate()
            if result:
                return result
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Condition was not met before timeout.")
            await asyncio.sleep(interval)

    return _wait_until


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session", autouse=True)
def migrated_database(settings) -> None:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def fixture_candles() -> dict[str, list[dict[str, object]]]:
    path = Path(__file__).resolve().parent / "fixtures" / "market_pipeline_candles.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def redis_client(settings) -> Iterator[Redis]:
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    yield client
    client.close()


@pytest.fixture(autouse=True)
def isolated_event_stream(redis_client: Redis, settings) -> Iterator[None]:
    redis_client.delete(settings.event_stream_name)
    for key in redis_client.scan_iter("iris:events:processed:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("iris:decision:*"):
        redis_client.delete(key)
    yield
    flush_publisher(timeout=2.0)
    redis_client.delete(settings.event_stream_name)
    for key in redis_client.scan_iter("iris:events:processed:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("iris:decision:*"):
        redis_client.delete(key)
    reset_event_publisher()


@pytest.fixture
def db_session() -> Iterator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def cleanup_test_coins() -> Iterator[None]:
    db = SessionLocal()
    try:
        db.execute(delete(Coin).where(Coin.symbol.in_(sorted(TEST_SYMBOLS.keys()))))
        db.commit()
        yield
    finally:
        db.execute(delete(Coin).where(Coin.symbol.in_(sorted(TEST_SYMBOLS.keys()))))
        db.commit()
        db.close()


@pytest.fixture
def seeded_market(db_session, fixture_candles):
    seeded: dict[str, dict[str, object]] = {}
    for target_symbol, (source_symbol, name) in TEST_SYMBOLS.items():
        coin = create_coin(
            db_session,
            CoinCreate(
                symbol=target_symbol,
                name=name,
                asset_type="crypto",
                theme="core",
                source="fixture",
            ),
        )
        bars = [
            MarketBar(
                timestamp=datetime.fromisoformat(str(item["timestamp"])),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item["volume"]) if item["volume"] is not None else None,
                source="fixture",
            )
            for item in fixture_candles[source_symbol]
        ]
        latest_timestamp = upsert_base_candles(db_session, coin, "15m", bars)
        coin.history_backfill_completed_at = utc_now()
        db_session.commit()
        seeded[target_symbol] = {
            "coin_id": coin.id,
            "source_symbol": source_symbol,
            "latest_timestamp": latest_timestamp,
        }
    return seeded
