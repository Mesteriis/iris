from __future__ import annotations

import json
import os
import sys
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL_SYS_PATH = list(sys.path)
sys.path = [
    path
    for path in _ORIGINAL_SYS_PATH
    if Path(path or ".").resolve() != _BACKEND_ROOT
]
from alembic.config import Config
import alembic.command as command
sys.path = _ORIGINAL_SYS_PATH
from redis import Redis
from sqlalchemy import delete, select

os.environ.setdefault("EVENT_STREAM_NAME", "iris_events_test")

from src.core.settings import get_settings

get_settings.cache_clear()

from src.core.db.session import AsyncSessionLocal, SessionLocal
from src.runtime.streams.publisher import flush_publisher, reset_event_publisher
from src.apps.anomalies.models import MarketAnomaly, MarketStructureSnapshot
from src.apps.control_plane.models import (
    EventRoute,
    EventRouteAuditLog,
    TopologyConfigVersion,
    TopologyDraft,
    TopologyDraftChange,
)
from src.apps.market_data.models import Coin
from src.apps.cross_market.models import CoinRelation
from src.apps.market_structure.models import MarketStructureSource
from src.apps.news.models import NewsItem, NewsItemLink, NewsSource
from src.apps.portfolio.models import ExchangeAccount
from src.apps.predictions.models import MarketPrediction
from src.apps.patterns.models import PatternFeature
from src.apps.patterns.models import PatternRegistry
from src.apps.patterns.models import PatternStatistic
from src.apps.hypothesis_engine.models import AIHypothesis, AIHypothesisEval, AIPrompt, AIWeight
from src.apps.portfolio.models import PortfolioAction
from src.apps.portfolio.models import PortfolioBalance
from src.apps.portfolio.models import PortfolioPosition
from src.apps.portfolio.models import PortfolioState
from src.apps.predictions.models import PredictionResult
from src.apps.cross_market.models import SectorMetric
from src.apps.market_data.schemas import CoinCreate
from src.apps.market_data.service_layer import create_coin
from src.apps.market_data.domain import utc_now
from src.apps.market_data.sources.base import MarketBar
from src.apps.market_data.repos import upsert_base_candles
from tests.factories.market_data import CoinCreateFactory

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
    config.set_main_option("script_location", str(backend_root / "src" / "migrations"))
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
    for key in redis_client.scan_iter("iris:portfolio:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("iris:correlation:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("iris:prediction:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("iris:ai:*"):
        redis_client.delete(key)
    yield
    flush_publisher(timeout=2.0)
    redis_client.delete(settings.event_stream_name)
    for key in redis_client.scan_iter("iris:events:processed:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("iris:decision:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("iris:portfolio:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("iris:correlation:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("iris:prediction:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("iris:ai:*"):
        redis_client.delete(key)
    reset_event_publisher()


@pytest.fixture
def db_session() -> Iterator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
async def async_db_session() -> AsyncIterator:
    async with AsyncSessionLocal() as db:
        yield db


@pytest.fixture(autouse=True)
def cleanup_test_coins() -> Iterator[None]:
    db = SessionLocal()
    try:
        db.execute(delete(Coin).where(Coin.symbol.endswith("_EVT")))
        db.commit()
        yield
    finally:
        db.execute(delete(Coin).where(Coin.symbol.endswith("_EVT")))
        db.commit()
        db.close()


@pytest.fixture(autouse=True)
def cleanup_portfolio_state() -> Iterator[None]:
    db = SessionLocal()
    try:
        db.execute(delete(SectorMetric))
        db.execute(delete(PredictionResult))
        db.execute(delete(MarketPrediction))
        db.execute(delete(CoinRelation))
        db.execute(delete(PortfolioAction))
        db.execute(delete(PortfolioPosition))
        db.execute(delete(PortfolioBalance))
        db.execute(delete(ExchangeAccount))
        db.execute(delete(PortfolioState))
        db.commit()
        yield
    finally:
        db.execute(delete(SectorMetric))
        db.execute(delete(PredictionResult))
        db.execute(delete(MarketPrediction))
        db.execute(delete(CoinRelation))
        db.execute(delete(PortfolioAction))
        db.execute(delete(PortfolioPosition))
        db.execute(delete(PortfolioBalance))
        db.execute(delete(ExchangeAccount))
        db.execute(delete(PortfolioState))
        db.commit()
        db.close()


@pytest.fixture(autouse=True)
def cleanup_pattern_state() -> Iterator[None]:
    db = SessionLocal()
    try:
        db.execute(delete(PatternStatistic))
        db.execute(delete(PatternRegistry))
        db.execute(delete(PatternFeature))
        db.commit()
        yield
    finally:
        db.execute(delete(PatternStatistic))
        db.execute(delete(PatternRegistry))
        db.execute(delete(PatternFeature))
        db.commit()
        db.close()


@pytest.fixture(autouse=True)
def cleanup_anomaly_state() -> Iterator[None]:
    db = SessionLocal()
    try:
        db.execute(delete(MarketStructureSnapshot))
        db.execute(delete(MarketAnomaly))
        db.commit()
        yield
    finally:
        db.execute(delete(MarketStructureSnapshot))
        db.execute(delete(MarketAnomaly))
        db.commit()
        db.close()


@pytest.fixture(autouse=True)
def cleanup_market_structure_state() -> Iterator[None]:
    db = SessionLocal()
    try:
        db.execute(delete(MarketStructureSource))
        db.commit()
        yield
    finally:
        db.execute(delete(MarketStructureSource))
        db.commit()
        db.close()


@pytest.fixture(autouse=True)
def cleanup_news_state() -> Iterator[None]:
    db = SessionLocal()
    try:
        db.execute(delete(NewsItemLink))
        db.execute(delete(NewsItem))
        db.execute(delete(NewsSource))
        db.commit()
        yield
    finally:
        db.execute(delete(NewsItemLink))
        db.execute(delete(NewsItem))
        db.execute(delete(NewsSource))
        db.commit()
        db.close()


@pytest.fixture(autouse=True)
def cleanup_hypothesis_state() -> Iterator[None]:
    db = SessionLocal()
    try:
        db.execute(delete(AIHypothesisEval))
        db.execute(delete(AIHypothesis))
        db.execute(delete(AIPrompt))
        db.execute(delete(AIWeight))
        db.commit()
        yield
    finally:
        db.execute(delete(AIHypothesisEval))
        db.execute(delete(AIHypothesis))
        db.execute(delete(AIPrompt))
        db.execute(delete(AIWeight))
        db.commit()
        db.close()


@pytest.fixture
def isolated_control_plane_state() -> Iterator[None]:
    db = SessionLocal()
    try:
        baseline_routes = {
            route.route_key: {
                "status": route.status,
                "scope_type": route.scope_type,
                "scope_value": route.scope_value,
                "environment": route.environment,
                "filters_json": dict(route.filters_json or {}),
                "throttle_config_json": dict(route.throttle_config_json or {}),
                "shadow_config_json": dict(route.shadow_config_json or {}),
                "notes": route.notes,
                "priority": int(route.priority),
                "system_managed": bool(route.system_managed),
                "event_definition_id": int(route.event_definition_id),
                "consumer_id": int(route.consumer_id),
            }
            for route in db.scalars(select(EventRoute).order_by(EventRoute.id.asc())).all()
        }
        yield
    finally:
        db.execute(delete(EventRouteAuditLog))
        db.execute(delete(TopologyDraftChange))
        db.execute(delete(TopologyDraft))
        db.execute(delete(EventRoute).where(EventRoute.system_managed.is_(False)))
        db.execute(delete(TopologyConfigVersion).where(TopologyConfigVersion.version_number > 1))
        routes = db.scalars(select(EventRoute).order_by(EventRoute.id.asc())).all()
        for route in routes:
            snapshot = baseline_routes.get(route.route_key)
            if snapshot is None:
                continue
            route.status = str(snapshot["status"])
            route.scope_type = str(snapshot["scope_type"])
            route.scope_value = snapshot["scope_value"]
            route.environment = str(snapshot["environment"])
            route.filters_json = dict(snapshot["filters_json"])
            route.throttle_config_json = dict(snapshot["throttle_config_json"])
            route.shadow_config_json = dict(snapshot["shadow_config_json"])
            route.notes = snapshot["notes"]
            route.priority = int(snapshot["priority"])
            route.system_managed = bool(snapshot["system_managed"])
            route.event_definition_id = int(snapshot["event_definition_id"])
            route.consumer_id = int(snapshot["consumer_id"])
        db.commit()
        db.close()


@pytest.fixture
def seeded_market(db_session, fixture_candles):
    seeded: dict[str, dict[str, object]] = {}
    for target_symbol, (source_symbol, name) in TEST_SYMBOLS.items():
        coin = create_coin(
            db_session,
            CoinCreateFactory.build(
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
