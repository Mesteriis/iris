# Python 3.14 Runtime Notes

## Status

This is a non-normative engineering note. Use ADRs and runtime policy documents for binding architectural rules.

## Scope

This document captures two Python `3.14` capabilities that are relevant to IRIS runtime operations:

- `asyncio ps` / `asyncio pstree` for live event-loop diagnostics
- subinterpreters for isolated CPU-bound execution inside a single process

## Why This Matters For IRIS

IRIS has two very different runtime shapes:

- long-lived async I/O paths:
  - FastAPI
  - WebSocket sessions
  - Redis Streams consumers
  - Task orchestration
- isolated compute-heavy paths:
  - scoring
  - aggregation
  - backtest-style calculations
  - candidate generation and ranking

Python `3.14` gives us a better diagnostics surface for the first category and a new standard-library concurrency option for the second.

## `asyncio ps` And `asyncio pstree`

Python `3.14` adds an `asyncio` command-line interface that can inspect a live Python process and show active asyncio tasks.

Useful commands:

```bash
python -m asyncio ps <PID>
python -m asyncio pstree <PID>
```

What they give us:

- active task inventory for a running process
- parent/child task tree instead of a flat dump
- a fast way to identify:
  - stuck awaits
  - leaked background tasks
  - fan-out explosions
  - queue consumers that stopped making progress
  - request handlers waiting on blocking downstream work

### When To Use In IRIS

Use these commands first when:

- WebSocket sessions stay open but stop receiving updates
- FastAPI endpoints become slow without obvious CPU saturation
- TaskIQ workers appear alive but stop draining queues
- shutdown hangs on pending tasks
- background orchestration creates more tasks than expected

### Typical IRIS Targets

- API process PID
- TaskIQ worker PID
- any long-lived Python process started from backend lifespan or worker bootstrap

### Practical Workflow

1. Find the backend or worker PID.
2. Run `python -m asyncio ps <PID>` to see all live tasks.
3. Run `python -m asyncio pstree <PID>` to understand parent/child relationships.
4. Match suspicious tasks to:
   - queue consumers
   - WebSocket broadcasters
   - request handlers
   - startup/background orchestration
5. Decide whether the issue is:
   - blocking I/O in the event loop
   - runaway task creation
   - missing cancellation
   - starvation on a shared queue or lock

### What This Does Not Solve

- it does not profile CPU hot loops
- it does not replace tracing or metrics
- it does not make blocking code safe in the event loop

This is a diagnostics surface, not a performance feature by itself.

## Subinterpreters

Python `3.14` adds a standard-library subinterpreter API through `concurrent.interpreters` and a higher-level executor in `concurrent.futures.InterpreterPoolExecutor`.

Relevant idea:

- each worker interpreter has its own interpreter state and its own GIL
- this allows true parallel execution for Python code across CPU cores
- unlike threads in the default build, this can help CPU-bound Python workloads

### Why This Is Interesting For IRIS

IRIS has some workloads that are poor fits for the main event loop and also awkward to keep as fully separate process topologies if the unit of work is relatively small.

Subinterpreters are worth considering for isolated pure-Python compute slices such as:

- hypothesis scoring or ranking passes
- signal aggregation batches
- pure-Python statistical transforms
- portfolio or market summary calculations that do not need shared mutable process state
- offline feature generation and validation steps

### What Makes Them Different From Threads

`ThreadPoolExecutor` in a normal CPython build still shares one GIL for Python bytecode.

`InterpreterPoolExecutor` is different:

- each worker runs in its own thread
- each thread owns a separate interpreter
- each interpreter has its own GIL

That means it can deliver real parallelism for CPU-heavy Python work, but only if the task is designed for isolation.

### What Makes Them Different From Processes

Compared with `ProcessPoolExecutor`, subinterpreters:

- stay inside one OS process
- have lower operational overhead than a full process boundary in some cases
- still force isolation of runtime state

But they are not a drop-in replacement for processes.

Tradeoffs:

- objects are not implicitly shared
- extension-module compatibility is not universal
- code has to be explicit about data handoff
- some workloads are still better served by separate processes

## Adoption Rules For IRIS

### Use `asyncio` Task Inspection Immediately

This is low risk and should become part of the normal runtime-debugging playbook for:

- API stalls
- worker hangs
- shutdown issues
- unexplained latency spikes in async services

### Use Subinterpreters Only For Narrow CPU-Bound Slices

Good candidates:

- deterministic pure-Python functions
- batch scoring with small and explicit inputs/outputs
- jobs that do not need ORM sessions, open sockets, or shared in-memory caches

Bad candidates:

- code that depends on shared mutable globals
- SQLAlchemy session work
- Redis clients and long-lived network connections
- extension-heavy code that is not known to be subinterpreter-safe
- request/response paths that need very low latency and high predictability

## Decision Table

| Tool | Best for | Avoid for |
|------|----------|-----------|
| `asyncio` | I/O-bound concurrency in API, WS, Redis, orchestration | CPU-heavy loops |
| `ThreadPoolExecutor` | blocking I/O adapters, short compatibility shims | Python CPU-bound work in default CPython |
| `ProcessPoolExecutor` | strong isolation, mature CPU parallelism | small high-frequency tasks with high IPC cost |
| `InterpreterPoolExecutor` | isolated pure-Python CPU tasks inside one process | shared-state, DB, network, extension-uncertain workloads |

## Proposed IRIS Plan

### Phase 1

- add `asyncio ps` / `pstree` to the backend operational runbook
- use it during real incident debugging before adding new instrumentation blindly

### Phase 2

- identify one CPU-heavy, pure-Python candidate workload
- build a benchmark harness for:
  - direct execution
  - `ThreadPoolExecutor`
  - `ProcessPoolExecutor`
  - `InterpreterPoolExecutor`
- compare:
  - wall-clock latency
  - CPU utilization
  - memory overhead
  - serialization cost

### Phase 3

- adopt subinterpreters only if benchmarks beat current worker/process alternatives
- keep DB access, Redis I/O, and API-side orchestration outside subinterpreters

## Important Non-Goal

This document is not a recommendation to adopt free-threaded Python builds across IRIS.

For now:

- the default `3.14.2` runtime still behaves like normal CPython with a GIL
- free-threaded Python is a separate deployment decision
- extension support and single-thread overhead make that a separate experiment

## External References

- [What’s New In Python 3.14](https://docs.python.org/3.14/whatsnew/3.14.html)
- [Python support for free threading](https://docs.python.org/3/howto/free-threading-python.html)
- [threading](https://docs.python.org/3.14/library/threading.html)
- [concurrent.interpreters](https://docs.python.org/3.14/library/concurrent.interpreters.html)
- [concurrent.futures.InterpreterPoolExecutor](https://docs.python.org/3.14/library/concurrent.futures.html)
