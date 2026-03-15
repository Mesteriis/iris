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
import alembic.command as command
from alembic.config import Config

sys.path = _ORIGINAL_SYS_PATH
from redis import Redis
from sqlalchemy import delete, func, select

os.environ.setdefault("EVENT_STREAM_NAME", "iris_events_test")

from src.core.settings import get_settings

get_settings.cache_clear()

from src.apps.anomalies.models import MarketAnomaly, MarketStructureSnapshot
from src.apps.briefs.models import AIBrief
from src.apps.control_plane.models import (
    EventConsumer,
    EventDefinition,
    EventRoute,
    EventRouteAuditLog,
    TopologyConfigVersion,
    TopologyDraft,
    TopologyDraftChange,
)
from src.apps.cross_market.models import CoinRelation, SectorMetric
from src.apps.explanations.models import AIExplanation
from src.apps.hypothesis_engine.models import AIHypothesis, AIHypothesisEval, AIPrompt, AIWeight
from src.apps.market_data.domain import utc_now
from src.apps.market_data.models import Coin
from src.apps.market_data.schemas import CoinCreate
from src.apps.market_data.sources.base import MarketBar
from src.apps.market_structure.models import MarketStructureSource
from src.apps.news.models import NewsItem, NewsItemLink, NewsSource
from src.apps.notifications.models import AINotification
from src.apps.patterns.models import PatternFeature, PatternRegistry, PatternStatistic
from src.apps.portfolio.models import (
    ExchangeAccount,
    PortfolioAction,
    PortfolioBalance,
    PortfolioPosition,
    PortfolioState,
)
from src.apps.predictions.models import MarketPrediction, PredictionResult
from src.core.db.session import AsyncSessionLocal, SessionLocal
from src.runtime.streams.publisher import flush_publisher, reset_event_publisher

from tests.factories.market_data import CoinCreateFactory, persist_coin
from tests.market_data_support import upsert_base_candles

TEST_SYMBOLS = {
    "BTCUSD_EVT": ("BTCUSD", "Bitcoin Event Test"),
    "ETHUSD_EVT": ("ETHUSD", "Ethereum Event Test"),
    "SOLUSD_EVT": ("SOLUSD", "Solana Event Test"),
}
_CONTROL_PLANE_BOOTSTRAP_NOTES = "Bootstrapped from legacy runtime router"
_AI_PROMPT_BASELINE: list[dict[str, object]] = []


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
    _snapshot_ai_prompt_baseline()


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
    for key in redis_client.scan_iter("iris:deliveries:*"):
        redis_client.delete(key)
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
    for key in redis_client.scan_iter("iris:control_plane:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("iris:http:operations:*"):
        redis_client.delete(key)
    yield
    flush_publisher(timeout=2.0)
    redis_client.delete(settings.event_stream_name)
    for key in redis_client.scan_iter("iris:deliveries:*"):
        redis_client.delete(key)
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
    for key in redis_client.scan_iter("iris:control_plane:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("iris:http:operations:*"):
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
def cleanup_notification_state() -> Iterator[None]:
    db = SessionLocal()
    try:
        db.execute(delete(AINotification))
        db.commit()
        yield
    finally:
        db.execute(delete(AINotification))
        db.commit()
        db.close()


@pytest.fixture(autouse=True)
def cleanup_brief_state() -> Iterator[None]:
    db = SessionLocal()
    try:
        db.execute(delete(AIBrief))
        db.commit()
        yield
    finally:
        db.execute(delete(AIBrief))
        db.commit()
        db.close()


@pytest.fixture(autouse=True)
def cleanup_explanation_state() -> Iterator[None]:
    db = SessionLocal()
    try:
        db.execute(delete(AIExplanation))
        db.commit()
        yield
    finally:
        db.execute(delete(AIExplanation))
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
        db.execute(delete(AIWeight))
        _restore_ai_prompt_baseline(db)
        db.commit()
        yield
    finally:
        db.execute(delete(AIHypothesisEval))
        db.execute(delete(AIHypothesis))
        db.execute(delete(AIWeight))
        _restore_ai_prompt_baseline(db)
        db.commit()
        db.close()


@pytest.fixture
def isolated_control_plane_state() -> Iterator[None]:
    db = SessionLocal()
    try:
        _restore_control_plane_baseline(db)
        yield
    finally:
        _restore_control_plane_baseline(db)
        db.close()


def _restore_control_plane_baseline(db) -> None:
    version = db.scalar(select(TopologyConfigVersion).where(TopologyConfigVersion.version_number == 1).limit(1))
    if version is None:
        db.commit()
        return

    snapshot_routes = list(version.snapshot_json.get("routes") or [])
    event_definition_id_by_type = {
        str(row.event_type): int(row.id)
        for row in db.execute(select(EventDefinition.id, EventDefinition.event_type))
    }
    consumer_id_by_key = {
        str(row.consumer_key): int(row.id)
        for row in db.execute(select(EventConsumer.id, EventConsumer.consumer_key))
    }

    db.execute(delete(EventRouteAuditLog))
    db.execute(delete(TopologyDraftChange))
    db.execute(delete(TopologyDraft))
    db.execute(delete(EventRoute))
    db.execute(delete(TopologyConfigVersion).where(TopologyConfigVersion.version_number > 1))
    db.flush()

    restored_routes: list[EventRoute] = []
    for route in snapshot_routes:
        route_key = str(route["route_key"])
        event_type = str(route["event_type"])
        consumer_key = str(route["consumer_key"])
        scope_value = route.get("scope_value")
        restored_route = EventRoute(
            route_key=route_key,
            event_definition_id=event_definition_id_by_type[event_type],
            consumer_id=consumer_id_by_key[consumer_key],
            status=str(route.get("status", "active")),
            scope_type=str(route.get("scope_type", "global")),
            scope_value=None if scope_value in (None, "*", "") else str(scope_value),
            environment=str(route.get("environment", "*")),
            filters_json=dict(route.get("filters") or {}),
            throttle_config_json=dict(route.get("throttle") or {}),
            shadow_config_json=dict(route.get("shadow") or {}),
            notes=str(route.get("notes") or _CONTROL_PLANE_BOOTSTRAP_NOTES),
            priority=int(route.get("priority", 100)),
            system_managed=bool(route.get("system_managed", True)),
        )
        db.add(restored_route)
        restored_routes.append(restored_route)
    db.flush()

    for restored_route, snapshot_route in zip(restored_routes, snapshot_routes, strict=True):
        db.add(
            EventRouteAuditLog(
                route_id=int(restored_route.id),
                route_key_snapshot=restored_route.route_key,
                draft_id=None,
                topology_version_id=int(version.id),
                action="bootstrapped",
                actor="system",
                actor_mode="control",
                reason="legacy_runtime_router_import",
                before_json={},
                after_json={
                    "event_type": str(snapshot_route["event_type"]),
                    "consumer_key": str(snapshot_route["consumer_key"]),
                    "status": restored_route.status,
                    "scope_type": restored_route.scope_type,
                    "environment": restored_route.environment,
                },
                context_json={"source": "legacy_runtime_router", "test_rehydrated": True},
            )
        )
    db.commit()


def _snapshot_ai_prompt_baseline() -> None:
    global _AI_PROMPT_BASELINE
    db = SessionLocal()
    try:
        rows = db.scalars(select(AIPrompt).order_by(AIPrompt.name.asc(), AIPrompt.version.asc(), AIPrompt.id.asc())).all()
        _AI_PROMPT_BASELINE = [
            {
                "name": str(row.name),
                "task": str(row.task),
                "version": int(row.version),
                "veil_lifted": bool(row.veil_lifted),
                "is_active": bool(row.is_active),
                "template": str(row.template),
                "vars_json": dict(row.vars_json or {}),
            }
            for row in rows
        ]
    finally:
        db.close()


def _restore_ai_prompt_baseline(db) -> None:
    db.execute(delete(AIPrompt))
    for row in _AI_PROMPT_BASELINE:
        db.add(
            AIPrompt(
                name=str(row["name"]),
                task=str(row["task"]),
                version=int(row["version"]),
                veil_lifted=bool(row["veil_lifted"]),
                is_active=bool(row["is_active"]),
                template=str(row["template"]),
                vars_json=dict(row["vars_json"]),
            )
        )
    db.flush()


@pytest.fixture(autouse=True)
def ensure_control_plane_audit_seed() -> Iterator[None]:
    db = SessionLocal()
    try:
        audit_count = int(db.scalar(select(func.count()).select_from(EventRouteAuditLog)) or 0)
        version = db.scalar(select(TopologyConfigVersion).where(TopologyConfigVersion.version_number == 1).limit(1))
        if audit_count == 0 and version is not None:
            routes = db.scalars(select(EventRoute).order_by(EventRoute.id.asc())).all()
            for route in routes:
                db.add(
                    EventRouteAuditLog(
                        route_id=int(route.id),
                        route_key_snapshot=route.route_key,
                        draft_id=None,
                        topology_version_id=int(version.id),
                        action="bootstrapped",
                        actor="system",
                        actor_mode="control",
                        reason="legacy_runtime_router_import",
                        before_json={},
                        after_json={
                            "event_definition_id": int(route.event_definition_id),
                            "consumer_id": int(route.consumer_id),
                            "status": route.status,
                            "scope_type": route.scope_type,
                            "environment": route.environment,
                        },
                        context_json={"source": "legacy_runtime_router", "test_rehydrated": True},
                    )
                )
            db.commit()
        yield
    finally:
        db.close()


@pytest.fixture
def seeded_market(db_session, fixture_candles):
    seeded: dict[str, dict[str, object]] = {}
    for target_symbol, (source_symbol, name) in TEST_SYMBOLS.items():
        coin = persist_coin(
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
