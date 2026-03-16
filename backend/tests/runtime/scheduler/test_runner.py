import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from src.runtime import scheduler as scheduler_pkg
from src.runtime.scheduler import runner


async def _fast_sleep(_seconds: float) -> None:
    return None


@pytest.mark.asyncio
async def test_schedule_history_backfills_bootstrap_and_due(monkeypatch) -> None:
    now = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
    due_values = iter([now - timedelta(seconds=1)])
    calls: list[object] = []
    stop_event = asyncio.Event()
    trigger_event = asyncio.Event()

    async def fake_next_due() -> datetime:
        return next(due_values)

    async def fake_enqueue(task: object) -> None:
        calls.append(task)
        if len(calls) >= 2:
            stop_event.set()

    monkeypatch.setattr(runner.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(runner.settings, "bootstrap_history_on_startup", True)
    monkeypatch.setattr(runner.market_data_tasks, "get_next_history_backfill_due_at", fake_next_due)
    monkeypatch.setattr(runner.market_data_services, "utc_now", lambda: now)
    monkeypatch.setattr(runner, "enqueue_task", fake_enqueue)

    await runner.schedule_history_backfills(stop_event, trigger_event)

    assert calls == [
        runner.market_data_tasks.bootstrap_observed_coins_history,
        runner.market_data_tasks.backfill_observed_coins_history,
    ]


@pytest.mark.asyncio
async def test_schedule_history_backfills_trigger_and_empty_queue(monkeypatch) -> None:
    now = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
    calls: list[object] = []
    stop_event = asyncio.Event()
    trigger_event = asyncio.Event()
    trigger_event.set()

    async def fake_enqueue(task: object) -> None:
        calls.append(task)
        stop_event.set()

    async def due_in_future() -> datetime:
        return now + timedelta(days=1)

    monkeypatch.setattr(runner.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(runner.settings, "bootstrap_history_on_startup", False)
    monkeypatch.setattr(
        runner.market_data_tasks,
        "get_next_history_backfill_due_at",
        due_in_future,
    )
    monkeypatch.setattr(runner.market_data_services, "utc_now", lambda: now)
    monkeypatch.setattr(runner, "enqueue_task", fake_enqueue)

    await runner.schedule_history_backfills(stop_event, trigger_event)

    assert calls == [runner.market_data_tasks.backfill_observed_coins_history]
    assert trigger_event.is_set() is False

    no_due_stop_event = asyncio.Event()
    no_due_trigger_event = asyncio.Event()
    no_due_calls: list[object] = []

    async def no_due() -> None:
        return None

    monkeypatch.setattr(
        runner.market_data_tasks,
        "get_next_history_backfill_due_at",
        no_due,
    )

    async def no_due_enqueue(task: object) -> None:
        no_due_calls.append(task)

    monkeypatch.setattr(runner, "enqueue_task", no_due_enqueue)

    asyncio.get_running_loop().call_soon(no_due_stop_event.set)
    await runner.schedule_history_backfills(no_due_stop_event, no_due_trigger_event)

    assert no_due_calls == []


@pytest.mark.asyncio
async def test_schedule_history_backfills_returns_immediately_when_stopped(monkeypatch) -> None:
    stop_event = asyncio.Event()
    trigger_event = asyncio.Event()
    stop_event.set()
    calls: list[object] = []

    monkeypatch.setattr(runner.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(runner, "enqueue_task", lambda task: asyncio.sleep(0, result=calls.append(task)))

    await runner.schedule_history_backfills(stop_event, trigger_event)

    assert calls == []


@pytest.mark.asyncio
async def test_schedule_history_backfills_continues_when_due_is_unknown(monkeypatch) -> None:
    now = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
    due_values = iter([None, now - timedelta(seconds=1)])
    calls: list[object] = []
    stop_event = asyncio.Event()
    trigger_event = asyncio.Event()

    class PendingTask:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    def fake_create_task(coro):
        coro.close()
        return PendingTask()

    async def fake_next_due():
        return next(due_values)

    async def fake_wait(tasks, timeout: float | None = None, return_when=None):
        del timeout, return_when
        return set(), set(tasks)

    async def fake_enqueue(task: object) -> None:
        calls.append(task)
        stop_event.set()

    monkeypatch.setattr(runner.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(runner.settings, "bootstrap_history_on_startup", False)
    monkeypatch.setattr(runner.market_data_tasks, "get_next_history_backfill_due_at", fake_next_due)
    monkeypatch.setattr(runner.market_data_services, "utc_now", lambda: now)
    monkeypatch.setattr(runner, "enqueue_task", fake_enqueue)
    monkeypatch.setattr(runner.asyncio, "wait", fake_wait)
    monkeypatch.setattr(runner.asyncio, "create_task", fake_create_task)

    await runner.schedule_history_backfills(stop_event, trigger_event)

    assert calls == [runner.market_data_tasks.backfill_observed_coins_history]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "function",
    [
        runner.enqueue_latest_price_snapshots,
        runner.schedule_pattern_statistics_refresh,
        runner.schedule_market_structure_refresh,
        runner.schedule_pattern_discovery_refresh,
        runner.schedule_strategy_discovery_refresh,
        runner.schedule_portfolio_sync,
        runner.schedule_prediction_evaluation,
        runner.schedule_news_poll,
        runner.schedule_hypothesis_evaluation,
        runner.schedule_market_structure_snapshot_poll,
        runner.schedule_market_structure_health_refresh,
    ],
)
async def test_periodic_schedulers_return_immediately_when_stopped(monkeypatch, function) -> None:
    stop_event = asyncio.Event()
    stop_event.set()
    calls: list[object] = []

    monkeypatch.setattr(runner.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(runner, "enqueue_task", lambda task: asyncio.sleep(0, result=calls.append(task)))

    await function(stop_event)

    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("function", "setting_name", "task_attr"),
    [
        ("enqueue_latest_price_snapshots", "taskiq_refresh_interval_seconds", "refresh_observed_coins_history"),
        ("schedule_pattern_statistics_refresh", "taskiq_pattern_statistics_interval_seconds", "pattern_evaluation_job"),
        ("schedule_market_structure_refresh", "taskiq_market_structure_interval_seconds", "refresh_market_structure"),
        ("schedule_pattern_discovery_refresh", "taskiq_pattern_discovery_interval_seconds", "run_pattern_discovery"),
        ("schedule_strategy_discovery_refresh", "taskiq_strategy_discovery_interval_seconds", "strategy_discovery_job"),
        ("schedule_portfolio_sync", "taskiq_portfolio_sync_interval_seconds", "portfolio_sync_job"),
        ("schedule_prediction_evaluation", "taskiq_prediction_evaluation_interval_seconds", "prediction_evaluation_job"),
        ("schedule_news_poll", "taskiq_news_poll_interval_seconds", "poll_enabled_news_sources_job"),
        ("schedule_hypothesis_evaluation", "taskiq_hypothesis_eval_interval_seconds", "evaluate_hypotheses_job"),
        ("schedule_market_structure_snapshot_poll", "taskiq_market_structure_snapshot_poll_interval_seconds", "poll_enabled_market_structure_sources_job"),
        ("schedule_market_structure_health_refresh", "taskiq_market_structure_health_interval_seconds", "refresh_market_structure_source_health_job"),
    ],
)
async def test_periodic_schedulers_wait_when_disabled(monkeypatch, function: str, setting_name: str, task_attr: str) -> None:
    stop_event = asyncio.Event()
    calls: list[object] = []

    monkeypatch.setattr(runner.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(runner.settings, setting_name, 0)

    async def fake_enqueue(task: object) -> None:
        calls.append(task)

    monkeypatch.setattr(runner, "enqueue_task", fake_enqueue)

    asyncio.get_running_loop().call_soon(stop_event.set)
    await getattr(runner, function)(stop_event)

    assert calls == []
    task_module = (
        runner.market_data_tasks
        if "refresh_observed" in task_attr
        else runner.market_structure_tasks
        if "market_structure_source" in task_attr
        else runner.pattern_tasks
        if "pattern" in task_attr or "strategy" in task_attr or "market_structure" in task_attr
        else runner.portfolio_tasks
        if "portfolio" in task_attr
        else runner.hypothesis_tasks
        if "hypoth" in task_attr
        else runner.news_tasks
        if "news" in task_attr
        else runner.prediction_tasks
    )
    assert getattr(task_module, task_attr)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("function", "setting_name", "task"),
    [
        (runner.enqueue_latest_price_snapshots, "taskiq_refresh_interval_seconds", runner.market_data_tasks.refresh_observed_coins_history),
        (runner.schedule_pattern_statistics_refresh, "taskiq_pattern_statistics_interval_seconds", runner.pattern_tasks.pattern_evaluation_job),
        (runner.schedule_market_structure_refresh, "taskiq_market_structure_interval_seconds", runner.pattern_tasks.refresh_market_structure),
        (runner.schedule_pattern_discovery_refresh, "taskiq_pattern_discovery_interval_seconds", runner.pattern_tasks.run_pattern_discovery),
        (runner.schedule_strategy_discovery_refresh, "taskiq_strategy_discovery_interval_seconds", runner.pattern_tasks.strategy_discovery_job),
        (runner.schedule_portfolio_sync, "taskiq_portfolio_sync_interval_seconds", runner.portfolio_tasks.portfolio_sync_job),
        (runner.schedule_prediction_evaluation, "taskiq_prediction_evaluation_interval_seconds", runner.prediction_tasks.prediction_evaluation_job),
        (runner.schedule_news_poll, "taskiq_news_poll_interval_seconds", runner.news_tasks.poll_enabled_news_sources_job),
        (runner.schedule_market_source_capability_refresh, "market_source_capability_refresh_interval_seconds", runner.market_data_tasks.refresh_market_source_capability_map),
        (runner.schedule_hypothesis_evaluation, "taskiq_hypothesis_eval_interval_seconds", runner.hypothesis_tasks.evaluate_hypotheses_job),
        (runner.schedule_market_structure_snapshot_poll, "taskiq_market_structure_snapshot_poll_interval_seconds", runner.market_structure_tasks.poll_enabled_market_structure_sources_job),
        (runner.schedule_market_structure_health_refresh, "taskiq_market_structure_health_interval_seconds", runner.market_structure_tasks.refresh_market_structure_source_health_job),
    ],
)
async def test_periodic_schedulers_enqueue_one_cycle(monkeypatch, function, setting_name: str, task: object) -> None:
    stop_event = asyncio.Event()
    calls: list[object] = []

    async def fake_wait_for(awaitable, timeout: float):
        assert timeout == 1
        awaitable.close()
        raise TimeoutError

    async def fake_enqueue(enqueued_task: object) -> None:
        calls.append(enqueued_task)
        stop_event.set()

    monkeypatch.setattr(runner.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(runner.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(runner.settings, setting_name, 1)
    if function is runner.schedule_market_source_capability_refresh:
        monkeypatch.setattr(runner.settings, "market_source_capability_refresh_on_startup", False)
    monkeypatch.setattr(runner, "enqueue_task", fake_enqueue)

    await function(stop_event)

    assert calls == [task]


@pytest.mark.asyncio
async def test_market_source_capability_scheduler_enqueues_startup_refresh(monkeypatch) -> None:
    stop_event = asyncio.Event()
    calls: list[object] = []

    async def fake_enqueue(enqueued_task: object) -> None:
        calls.append(enqueued_task)
        stop_event.set()

    monkeypatch.setattr(runner.asyncio, "sleep", _fast_sleep)
    monkeypatch.setattr(runner.settings, "market_source_capability_refresh_on_startup", True)
    monkeypatch.setattr(runner.settings, "market_source_capability_refresh_interval_seconds", 3600)
    monkeypatch.setattr(runner, "enqueue_task", fake_enqueue)

    await runner.schedule_market_source_capability_refresh(stop_event)

    assert calls == [runner.market_data_tasks.refresh_market_source_capability_map]


def test_start_scheduler_assigns_created_tasks(monkeypatch) -> None:
    created_tasks: list[object] = []

    def fake_create_task(coro):
        coro.close()
        task = object()
        created_tasks.append(task)
        return task

    monkeypatch.setattr(runner.asyncio, "create_task", fake_create_task)

    app = SimpleNamespace(state=SimpleNamespace())
    finish_event = asyncio.Event()
    backfill_event = asyncio.Event()

    tasks = runner.start_scheduler(app, finish_event=finish_event, backfill_event=backfill_event)

    assert tuple(tasks) == tuple(created_tasks)
    assert app.state.taskiq_backfill_task is created_tasks[0]
    assert app.state.taskiq_prediction_evaluation_task is created_tasks[-6]
    assert app.state.taskiq_news_poll_task is created_tasks[-5]
    assert app.state.taskiq_market_source_capability_refresh_task is created_tasks[-4]
    assert app.state.taskiq_hypothesis_evaluation_task is created_tasks[-3]
    assert app.state.taskiq_market_structure_snapshot_poll_task is created_tasks[-2]
    assert app.state.taskiq_market_structure_health_task is created_tasks[-1]
    assert scheduler_pkg.start_scheduler is runner.start_scheduler
    assert scheduler_pkg.schedule_history_backfills is runner.schedule_history_backfills
