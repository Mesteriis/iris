from __future__ import annotations

import asyncio
import runpy
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

import app.core.bootstrap.app as bootstrap_app_module
import app.core.bootstrap.lifespan as lifespan_module
import app.core.db.session as session_module
import app.core.db.uow as uow_module
import app.core.settings.base as settings_base_module
import app.main as main_module


def test_bootstrap_app_builds_config_runs_migrations_and_enters_deferred_lifespan(monkeypatch) -> None:
    config = bootstrap_app_module.get_alembic_config()
    assert config.get_main_option("script_location").endswith("/backend/alembic")
    assert config.get_main_option("sqlalchemy.url") == bootstrap_app_module.settings.database_url

    upgrade_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        bootstrap_app_module.command,
        "upgrade",
        lambda cfg, revision: upgrade_calls.append((cfg.get_main_option("script_location"), revision)),
    )
    bootstrap_app_module.run_migrations()
    assert upgrade_calls == [(config.get_main_option("script_location"), "head")]

    entered: list[object] = []

    @asynccontextmanager
    async def _fake_lifespan(app: FastAPI):
        entered.append(app)
        yield
        entered.append("closed")

    monkeypatch.setattr("app.core.bootstrap.lifespan.lifespan", _fake_lifespan)
    app = bootstrap_app_module.create_app()
    assert app.title == bootstrap_app_module.settings.app_name
    assert callable(app.state.run_migrations)
    assert any(route.path == "/status" for route in app.routes)
    assert any(middleware.cls.__name__ == "CORSMiddleware" for middleware in app.user_middleware)

    async def _exercise() -> None:
        async with app.router.lifespan_context(app):
            entered.append("inside")

    asyncio.run(_exercise())
    assert entered[0] is app
    assert entered[1:] == ["inside", "closed"]


@pytest.mark.asyncio
async def test_lifespan_orchestrates_startup_and_shutdown(monkeypatch) -> None:
    events: list[object] = []

    async def _wait_db():
        events.append("wait_db")

    async def _wait_redis():
        events.append("wait_redis")

    class _Broker:
        def __init__(self, name: str) -> None:
            self.name = name

        async def startup(self) -> None:
            events.append(f"{self.name}_startup")

        async def shutdown(self) -> None:
            events.append(f"{self.name}_shutdown")

    class _Carousel:
        async def close(self) -> None:
            events.append("carousel_close")

    async def _fake_to_thread(func, *args):
        events.append(("to_thread", getattr(func, "__name__", repr(func))))
        return func(*args)

    def _spawn_taskiq():
        events.append("spawn_taskiq")
        return "taskiq_stop", ["taskiq_worker"]

    def _spawn_streams():
        events.append("spawn_streams")
        return "stream_stop", ["stream_worker"]

    def _stop_taskiq(stop_event, processes):
        events.append(("stop_taskiq", stop_event, tuple(processes)))

    def _stop_streams(stop_event, processes):
        events.append(("stop_streams", stop_event, tuple(processes)))

    async def _close_lock_client():
        events.append("close_lock_client")

    monkeypatch.setattr(lifespan_module, "wait_for_database", _wait_db)
    monkeypatch.setattr(lifespan_module, "wait_for_redis", _wait_redis)
    monkeypatch.setattr(lifespan_module, "broker", _Broker("broker"))
    monkeypatch.setattr(lifespan_module, "analytics_broker", _Broker("analytics"))
    monkeypatch.setattr(lifespan_module.asyncio, "to_thread", _fake_to_thread)
    monkeypatch.setattr(lifespan_module, "spawn_taskiq_worker_processes", _spawn_taskiq)
    monkeypatch.setattr(lifespan_module, "spawn_event_worker_processes", _spawn_streams)
    monkeypatch.setattr(lifespan_module, "stop_taskiq_worker_processes", _stop_taskiq)
    monkeypatch.setattr(lifespan_module, "stop_event_worker_processes", _stop_streams)
    monkeypatch.setattr(lifespan_module, "register_default_receivers", lambda: events.append("register_receivers"))
    monkeypatch.setattr(lifespan_module, "reset_message_bus", lambda: events.append("reset_bus"))
    monkeypatch.setattr(lifespan_module, "reset_event_publisher", lambda: events.append("reset_publisher"))
    monkeypatch.setattr(lifespan_module, "close_async_task_lock_client", _close_lock_client)
    monkeypatch.setattr(lifespan_module, "get_market_source_carousel", lambda: _Carousel())

    scheduler_task = asyncio.create_task(asyncio.sleep(0))

    def _start_scheduler(app, *, finish_event, backfill_event):
        events.append(("start_scheduler", finish_event.is_set(), backfill_event.is_set()))
        return [scheduler_task]

    monkeypatch.setattr(lifespan_module, "start_scheduler", _start_scheduler)

    app = FastAPI()
    app.state.run_migrations = lambda: events.append("run_migrations")

    async with lifespan_module.lifespan(app):
        assert app.state.taskiq_worker_stop_event == "taskiq_stop"
        assert app.state.taskiq_worker_processes == ["taskiq_worker"]
        assert app.state.event_worker_stop_event == "stream_stop"
        assert app.state.event_worker_processes == ["stream_worker"]
        assert hasattr(app.state, "taskiq_finish_event")
        assert hasattr(app.state, "taskiq_backfill_event")

    assert "wait_db" in events
    assert "wait_redis" in events
    assert "broker_startup" in events
    assert "analytics_startup" in events
    assert "run_migrations" in events
    assert ("stop_taskiq", "taskiq_stop", ("taskiq_worker",)) in events
    assert ("stop_streams", "stream_stop", ("stream_worker",)) in events
    assert "analytics_shutdown" in events
    assert "broker_shutdown" in events
    assert "reset_bus" in events
    assert "reset_publisher" in events
    assert "close_lock_client" in events
    assert "carousel_close" in events


@pytest.mark.asyncio
async def test_db_session_helpers_wait_logic_and_async_uow(monkeypatch) -> None:
    class _DummyAsyncSession:
        def __init__(self) -> None:
            self.closed = 0
            self.commits = 0
            self.rollbacks = 0

        async def close(self) -> None:
            self.closed += 1

        async def commit(self) -> None:
            self.commits += 1

        async def rollback(self) -> None:
            self.rollbacks += 1

    dummy_session = _DummyAsyncSession()
    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: dummy_session)
    db_gen = session_module.get_db()
    yielded = await anext(db_gen)
    assert yielded is dummy_session
    with pytest.raises(StopAsyncIteration):
        await anext(db_gen)
    assert dummy_session.closed == 1

    executed: list[str] = []

    class _Connection:
        async def __aenter__(self):
            executed.append("enter")
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            executed.append("exit")
            return False

        async def execute(self, statement) -> None:
            executed.append(str(statement))

    monkeypatch.setattr(session_module, "async_engine", SimpleNamespace(connect=lambda: _Connection()))
    await session_module.ping_database()
    assert executed == ["enter", "SELECT 1", "exit"]

    attempts = {"count": 0}
    sleep_calls: list[float] = []

    async def _sleep(delay: float) -> None:
        sleep_calls.append(delay)

    async def _ping_once_then_succeed() -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary")

    monkeypatch.setattr(session_module, "ping_database", _ping_once_then_succeed)
    monkeypatch.setattr(session_module.settings, "database_connect_retries", 2, raising=False)
    monkeypatch.setattr(session_module.settings, "database_connect_retry_delay", 0.0, raising=False)
    monkeypatch.setattr(session_module.asyncio, "sleep", _sleep)
    await session_module.wait_for_database()
    assert attempts["count"] == 2
    assert sleep_calls == [0.0]

    async def _always_fail() -> None:
        raise RuntimeError("permanent")

    monkeypatch.setattr(session_module, "ping_database", _always_fail)
    monkeypatch.setattr(session_module.settings, "database_connect_retries", 2, raising=False)
    with pytest.raises(RuntimeError, match="permanent"):
        await session_module.wait_for_database()

    monkeypatch.setattr(session_module.settings, "database_connect_retries", 0, raising=False)
    await session_module.wait_for_database()

    commit_session = _DummyAsyncSession()
    rollback_session = _DummyAsyncSession()
    scoped_session = _DummyAsyncSession()
    sessions = iter([commit_session, rollback_session, scoped_session])
    monkeypatch.setattr(uow_module, "AsyncSessionLocal", lambda: next(sessions))

    async with uow_module.AsyncUnitOfWork() as uow:
        assert uow.session is commit_session
    assert commit_session.commits == 1
    assert commit_session.rollbacks == 0
    assert commit_session.closed == 1

    with pytest.raises(ValueError):
        async with uow_module.AsyncUnitOfWork():
            raise ValueError("boom")
    assert rollback_session.commits == 0
    assert rollback_session.rollbacks == 1
    assert rollback_session.closed == 1

    async with uow_module.async_session_scope() as session:
        assert session is scoped_session
    assert scoped_session.commits == 1
    assert scoped_session.closed == 2


def test_main_run_invokes_uvicorn(monkeypatch) -> None:
    calls: list[tuple[str, str, int]] = []
    monkeypatch.setattr(main_module.uvicorn, "run", lambda target, host, port: calls.append((target, host, port)))
    main_module.run()
    assert calls == [("app.main:app", main_module.settings.api_host, main_module.settings.api_port)]


def test_settings_validator_and_main_module_entrypoint(monkeypatch) -> None:
    assert settings_base_module.Settings.normalize_origins(["http://localhost:3000"]) == ["http://localhost:3000"]

    calls: list[tuple[str, str, int]] = []
    monkeypatch.setattr("uvicorn.run", lambda target, host, port: calls.append((target, host, port)))
    original_main = sys.modules.pop("app.main", None)
    runpy.run_module("app.main", run_name="__main__")
    if original_main is not None:
        sys.modules["app.main"] = original_main
    assert calls
