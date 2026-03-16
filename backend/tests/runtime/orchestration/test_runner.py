import asyncio
from types import SimpleNamespace

import pytest
from iris.runtime.orchestration import runner


class _StopFlag:
    def __init__(self, *, initially_set: bool = False) -> None:
        self._is_set = initially_set

    def is_set(self) -> bool:
        return self._is_set

    def set(self) -> None:
        self._is_set = True


@pytest.mark.asyncio
async def test_watch_stop_flag_sets_finish_event(monkeypatch) -> None:
    async def fast_sleep(_seconds: float) -> None:
        stop_flag.set()

    stop_flag = _StopFlag()
    finish_event = asyncio.Event()
    monkeypatch.setattr(runner.asyncio, "sleep", fast_sleep)

    await runner._watch_stop_flag(stop_flag, finish_event)

    assert finish_event.is_set() is True


def test_load_worker_broker_and_group_definitions() -> None:
    general = runner._load_worker_broker("taskiq-general")
    analytics = runner._load_worker_broker("taskiq-analytics")

    assert general is not analytics
    assert any(group.name == "taskiq-general" for group in runner.TASKIQ_WORKER_GROUPS)
    assert any(group.name == "taskiq-analytics" for group in runner.TASKIQ_WORKER_GROUPS)

    with pytest.raises(ValueError, match="Unsupported TaskIQ worker group"):
        runner._load_worker_broker("unsupported")


@pytest.mark.asyncio
async def test_serve_taskiq_worker_listener_finishes_first(monkeypatch) -> None:
    calls: list[str] = []

    class FakeBroker:
        async def startup(self) -> None:
            calls.append("startup")

        async def shutdown(self) -> None:
            calls.append("shutdown")

    class FakeReceiver:
        def __init__(self, *, broker, run_startup: bool) -> None:
            calls.append(f"receiver:{run_startup}")
            self.broker = broker

        async def listen(self, finish_event: asyncio.Event) -> str:
            finish_event.set()
            calls.append("listen")
            return "done"

    class FakeSourceCapabilityRegistry:
        async def start(self) -> None:
            calls.append("registry_start")

        async def stop(self) -> None:
            calls.append("registry_stop")

    monkeypatch.setattr(runner, "_load_worker_broker", lambda group_name: FakeBroker())
    monkeypatch.setattr(runner, "Receiver", FakeReceiver)
    monkeypatch.setattr(runner, "get_market_source_capability_registry", lambda: FakeSourceCapabilityRegistry())

    await runner._serve_taskiq_worker("taskiq-general", _StopFlag())

    assert calls == ["startup", "registry_start", "receiver:False", "listen", "registry_stop", "shutdown"]


@pytest.mark.asyncio
async def test_serve_taskiq_worker_stop_flag_finishes_first(monkeypatch) -> None:
    calls: list[str] = []

    class FakeBroker:
        async def startup(self) -> None:
            calls.append("startup")

        async def shutdown(self) -> None:
            calls.append("shutdown")

    class FakeReceiver:
        def __init__(self, *, broker, run_startup: bool) -> None:
            calls.append(f"receiver:{run_startup}")
            self.broker = broker

        async def listen(self, finish_event: asyncio.Event) -> str:
            await finish_event.wait()
            await asyncio.sleep(0)
            calls.append("listen")
            return "stopped"

    class FakeSourceCapabilityRegistry:
        async def start(self) -> None:
            calls.append("registry_start")

        async def stop(self) -> None:
            calls.append("registry_stop")

    monkeypatch.setattr(runner, "_load_worker_broker", lambda group_name: FakeBroker())
    monkeypatch.setattr(runner, "Receiver", FakeReceiver)
    monkeypatch.setattr(runner, "get_market_source_capability_registry", lambda: FakeSourceCapabilityRegistry())
    original_wait = runner.asyncio.wait

    async def fake_wait(tasks, *, return_when):
        done, pending = await original_wait(tasks, return_when=return_when)
        watcher = next(task for task in done | pending if "_watch_stop_flag" in task.get_coro().__qualname__)
        listener = next(task for task in done | pending if "listen" in task.get_coro().__qualname__)
        return {watcher}, {listener}

    monkeypatch.setattr(runner.asyncio, "wait", fake_wait)

    await runner._serve_taskiq_worker("taskiq-general", _StopFlag(initially_set=True))

    assert calls == ["startup", "registry_start", "receiver:False", "listen", "registry_stop", "shutdown"]


def test_run_group_with_stop_wraps_async_worker(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    async def fake_serve(group_name: str, stop_flag: object) -> None:
        calls.append((group_name, stop_flag))

    monkeypatch.setattr(runner, "_serve_taskiq_worker", fake_serve)
    monkeypatch.setattr(runner.signal, "signal", lambda *_args, **_kwargs: None)

    stop_flag = _StopFlag()
    runner._run_group_with_stop("taskiq-general", stop_flag)

    assert calls == [("taskiq-general", stop_flag)]


def test_spawn_and_stop_taskiq_worker_processes(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self, *, target, args, daemon: bool, name: str) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon
            self.name = name
            self.started = False
            self.join_timeouts: list[float] = []
            self.terminated = False
            self.alive = name.endswith("-2")

        def start(self) -> None:
            self.started = True

        def join(self, timeout: float | None = None) -> None:
            if timeout is not None:
                self.join_timeouts.append(timeout)

        def is_alive(self) -> bool:
            return self.alive

        def terminate(self) -> None:
            self.terminated = True
            self.alive = False

    class FakeContext:
        def __init__(self) -> None:
            self.processes: list[FakeProcess] = []
            self.event = _StopFlag()

        def Event(self) -> _StopFlag:
            return self.event

        def Process(self, *, target, args, daemon: bool, name: str) -> FakeProcess:
            process = FakeProcess(target=target, args=args, daemon=daemon, name=name)
            self.processes.append(process)
            return process

    fake_context = FakeContext()
    monkeypatch.setattr(runner.multiprocessing, "get_context", lambda mode: fake_context)
    monkeypatch.setattr(
        runner,
        "TASKIQ_WORKER_GROUPS",
        (
            runner.TaskiqWorkerGroup(name="taskiq-general", process_count=1),
            runner.TaskiqWorkerGroup(name="taskiq-analytics", process_count=2),
        ),
    )

    stop_event, processes = runner.spawn_taskiq_worker_processes()

    assert stop_event is fake_context.event
    assert len(processes) == 3
    assert all(process.started for process in processes)

    runner.stop_taskiq_worker_processes(stop_event, processes)

    assert stop_event.is_set() is True
    assert processes[0].terminated is False
    assert processes[1].terminated is False
    assert processes[2].terminated is True
