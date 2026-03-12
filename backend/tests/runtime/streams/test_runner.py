from __future__ import annotations

from src.runtime.streams import runner


class _Worker:
    def __init__(self) -> None:
        self.run_calls: list[object] = []
        self.closed = False
        self.stopped = False

    def run(self, *, stop_checker=None) -> None:
        self.run_calls.append(stop_checker)
        if stop_checker is not None:
            stop_checker()

    def close(self) -> None:
        self.closed = True

    def stop(self) -> None:
        self.stopped = True


class _StopFlag:
    def __init__(self) -> None:
        self._is_set = False

    def is_set(self) -> bool:
        return self._is_set

    def set(self) -> None:
        self._is_set = True


def test_run_worker_loop_and_run_group_with_stop(monkeypatch) -> None:
    first_worker = _Worker()
    second_worker = _Worker()
    dispatcher_worker = _Worker()
    workers = iter([first_worker, second_worker])
    handlers: list[object] = []

    monkeypatch.setattr(runner, "create_worker", lambda group_name: next(workers))
    monkeypatch.setattr(runner, "create_topology_dispatcher_consumer", lambda: dispatcher_worker)
    monkeypatch.setattr(runner.signal, "signal", lambda sig, handler: handlers.append(handler))

    runner.run_worker_loop("indicator_workers")

    stop_flag = _StopFlag()
    runner._run_group_with_stop("analysis_scheduler_workers", stop_flag)
    runner._run_topology_dispatcher_with_stop(stop_flag)

    assert first_worker.run_calls == [None]
    assert first_worker.closed is True
    assert second_worker.closed is True
    assert second_worker.stopped is True
    assert dispatcher_worker.closed is True
    assert dispatcher_worker.stopped is True
    assert callable(second_worker.run_calls[0])
    assert len(handlers) == 4


def test_spawn_and_stop_event_worker_processes(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self, *, target, args, daemon: bool, name: str) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon
            self.name = name
            self.started = False
            self.join_timeouts: list[float] = []
            self.terminated = False
            self.alive = name.startswith("iris-indicator")

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
    monkeypatch.setattr(runner, "EVENT_WORKER_GROUPS", ("indicator_workers", "pattern_workers"))

    stop_event, processes = runner.spawn_event_worker_processes()

    assert stop_event is fake_context.event
    assert len(processes) == 3
    assert processes[0].name == "iris-control-plane-dispatcher"
    assert all(process.started for process in processes)

    runner.stop_event_worker_processes(stop_event, processes)

    assert stop_event.is_set() is True
    assert processes[1].terminated is True
    assert processes[2].terminated is False
