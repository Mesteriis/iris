# IRIS Persistence Audit

Date: 2026-03-12

## Scope

This audit covers runtime application code under `backend/src` and excludes Alembic migrations, where raw SQL remains an acceptable schema-management tool.

Audit method:

- `rg` over `AsyncSession`, `Session`, `.execute(`, `text(`, `.commit(`, `.rollback(`, `.flush(`.
- manual review of `core/db`, async-first domains, and representative sync-heavy analytical domains.
- classification by persistence responsibility and migration priority.

## Executive Summary

The repository already contains useful persistence building blocks:

- `backend/src/core/db/session.py` centralizes engine and session creation.
- `backend/src/core/db/uow.py` introduces a minimal async unit of work.
- `backend/src/apps/control_plane/repositories.py` and `backend/src/apps/anomalies/repos/anomaly_repo.py` show early repository patterns.

The current state is still non-uniform and violates the target standard in several ways:

- direct `AsyncSession` and sync `Session` usage is widespread across `views`, `services`, `tasks`, `selectors`, and domain engines.
- repository boundaries are inconsistent: some domains use repositories, many still run ORM/Core queries directly inside application services or HTTP handlers.
- transaction ownership is fragmented: `commit()` and `flush()` are called from repositories, services, selectors, engines, workers, and tasks.
- read paths often return ORM entities or ad-hoc `dict[str, Any]` instead of immutable typed read models.
- raw SQL is concentrated in `market_data` for Timescale continuous aggregates and resampling logic, with no explicit exception policy documented yet.
- loading policy is not standardized; several list/detail paths still rely on caller-side serialization from ORM entities, which keeps lazy-loading/N+1 risk alive.
- persistence logging is largely absent outside a few unrelated runtime loggers.

## Quantitative Snapshot

Observed non-migration files with DB access or transaction ownership:

- files importing `AsyncSession` or `Session`: 80+
- files calling `commit()`, `rollback()`, or `flush()`: 40+
- files using `text(...)` or direct raw SQL execution: concentrated in `market_data`, plus a few infrastructure helpers

These counts are intentionally directional rather than contractual; the important result is the domain map below.

## Domain Classification

### Aligned or Partially Aligned

#### `apps/control_plane`

Status: partially aligned

- Existing repositories are present in [backend/src/apps/control_plane/repositories.py](/Users/avm/projects/Personal/iris/backend/src/apps/control_plane/repositories.py).
- Queries already use explicit eager loading for route/detail reads.
- Remaining issues:
  - services still own direct `commit()` / `flush()` logic.
  - read paths still leak ORM entities into views.
  - no immutable read models or shared persistence logging.

Classification:

- `move to query service`
- `replace ORM leakage with typed model`
- `fix transaction boundary`
- `add logging`

#### `apps/anomalies`

Status: partially aligned

- Repository exists in [backend/src/apps/anomalies/repos/anomaly_repo.py](/Users/avm/projects/Personal/iris/backend/src/apps/anomalies/repos/anomaly_repo.py).
- Read-heavy detection context is already isolated reasonably well.
- Remaining issues:
  - selectors return ORM entities.
  - service still commits directly.
  - no standardized immutable read contracts or persistence logging.

Classification:

- `move to query service`
- `replace ORM leakage with typed model`
- `fix transaction boundary`
- `add logging`

#### `apps/hypothesis_engine`

Status: migration-ready and high-value

- Small async-first domain with existing repository and tests.
- Current violations:
  - repository commits on `create_*`.
  - views instantiate repository directly.
  - services return ORM-backed responses.
  - prompt loading still reaches DB directly through helper code.
  - no explicit read/write contract split.

Classification:

- `move to repository`
- `move to query service`
- `replace ORM leakage with typed model`
- `fix transaction boundary`
- `add logging`

### Async Domains with Direct Persistence in Services

#### `apps/news`

Primary files:

- [backend/src/apps/news/services.py](/Users/avm/projects/Personal/iris/backend/src/apps/news/services.py)
- [backend/src/apps/news/pipeline.py](/Users/avm/projects/Personal/iris/backend/src/apps/news/pipeline.py)
- [backend/src/apps/news/views.py](/Users/avm/projects/Personal/iris/backend/src/apps/news/views.py)

Issues:

- service class mixes reads, writes, orchestration, and serialization.
- direct commits inside service and pipeline.
- read endpoints serialize ORM entities with `selectinload`, but still depend on ORM models as public contract.

Classification:

- `move to repository`
- `move to query service`
- `replace ORM leakage with typed model`
- `fix transaction boundary`
- `fix N+1/loading contract`
- `add logging`

#### `apps/market_structure`

Primary files:

- [backend/src/apps/market_structure/services.py](/Users/avm/projects/Personal/iris/backend/src/apps/market_structure/services.py)
- [backend/src/apps/market_structure/views.py](/Users/avm/projects/Personal/iris/backend/src/apps/market_structure/views.py)

Issues:

- one large service owns persistence, orchestration, serialization, and event publishing.
- direct commits across multiple write paths.
- read methods still return ORM-backed results after inline serialization.
- no repository/query service separation.

Classification:

- `move to repository`
- `move to query service`
- `fix transaction boundary`
- `fix N+1/loading contract`
- `replace ORM leakage with typed model`
- `add logging`

#### `apps/market_data`

Primary files:

- [backend/src/apps/market_data/services.py](/Users/avm/projects/Personal/iris/backend/src/apps/market_data/services.py)
- [backend/src/apps/market_data/service_layer.py](/Users/avm/projects/Personal/iris/backend/src/apps/market_data/service_layer.py)
- [backend/src/apps/market_data/repos.py](/Users/avm/projects/Personal/iris/backend/src/apps/market_data/repos.py)
- [backend/src/apps/market_data/views.py](/Users/avm/projects/Personal/iris/backend/src/apps/market_data/views.py)

Issues:

- both sync and async persistence paths coexist.
- services and service_layer both perform persistence, creating two public styles.
- raw SQL is used for Timescale aggregate views, resampling, and `refresh_continuous_aggregate`.
- commit ownership is spread across service functions.

Classification:

- `move to repository`
- `move to query service`
- `rewrite raw SQL to Core` where dynamic view access does not require vendor SQL
- `keep as justified raw SQL exception` for Timescale continuous aggregate refresh and dynamic aggregate-view reads/resampling
- `fix transaction boundary`
- `add logging`

### Sync-Heavy Analytical Domains

These domains are still dominated by synchronous `Session` access inside selectors/engines and represent the largest remaining migration surface:

- `apps/indicators`
- `apps/patterns`
- `apps/signals`
- `apps/portfolio`
- `apps/predictions`
- `apps/cross_market`

Shared issues:

- business logic and persistence are tightly coupled.
- read paths frequently return ad-hoc dictionaries.
- engines/selectors call `commit()` directly.
- some methods are N+1-prone because they load base rows and then perform follow-up scalar lookups inside loops.
- sync-only execution paths complicate the async-first target.

Classification:

- `move to repository`
- `move to query service`
- `replace ORM leakage with typed model`
- `fix transaction boundary`
- `fix N+1/loading contract`
- `add logging`

Priority note:

- these domains should migrate after the async-first domains because they require both boundary cleanup and sync-to-async strategy decisions.

## Cross-Cutting Findings

### Direct DB Access from API Surface

Direct session injection exists in multiple route modules, including:

- [backend/src/apps/hypothesis_engine/views.py](/Users/avm/projects/Personal/iris/backend/src/apps/hypothesis_engine/views.py)
- [backend/src/apps/control_plane/views.py](/Users/avm/projects/Personal/iris/backend/src/apps/control_plane/views.py)
- [backend/src/apps/news/views.py](/Users/avm/projects/Personal/iris/backend/src/apps/news/views.py)
- [backend/src/apps/market_structure/views.py](/Users/avm/projects/Personal/iris/backend/src/apps/market_structure/views.py)
- [backend/src/apps/market_data/views.py](/Users/avm/projects/Personal/iris/backend/src/apps/market_data/views.py)

Required action:

- replace route-level session usage with query services and command/application services built on top of a shared unit of work dependency.

### Transaction Boundary Drift

Representative offenders:

- [backend/src/apps/hypothesis_engine/repos/hypothesis_repo.py](/Users/avm/projects/Personal/iris/backend/src/apps/hypothesis_engine/repos/hypothesis_repo.py)
- [backend/src/apps/news/services.py](/Users/avm/projects/Personal/iris/backend/src/apps/news/services.py)
- [backend/src/apps/market_structure/services.py](/Users/avm/projects/Personal/iris/backend/src/apps/market_structure/services.py)
- [backend/src/apps/market_data/services.py](/Users/avm/projects/Personal/iris/backend/src/apps/market_data/services.py)
- [backend/src/apps/patterns/selectors.py](/Users/avm/projects/Personal/iris/backend/src/apps/patterns/selectors.py)
- [backend/src/apps/portfolio/engine.py](/Users/avm/projects/Personal/iris/backend/src/apps/portfolio/engine.py)

Required action:

- repositories may `flush()` when required for generated IDs or lock sequencing.
- application services / workers / tasks must own `commit()` and `rollback()`.
- query services must never commit.

### ORM Leakage and Untyped Read Contracts

Representative offenders:

- control-plane services/views return ORM routes and drafts.
- hypothesis views return ORM prompt/hypothesis/eval entities through Pydantic.
- selectors in `patterns`, `signals`, and `portfolio` return `dict[str, Any]`.

Required action:

- default read contract becomes immutable dataclass read models.
- mutable ORM access must be explicit via write-side repository methods such as `get_for_update(...)`.

### Raw SQL Status

Current raw SQL outside migrations is concentrated in:

- [backend/src/apps/market_data/repos.py](/Users/avm/projects/Personal/iris/backend/src/apps/market_data/repos.py)
- [backend/src/apps/market_data/services.py](/Users/avm/projects/Personal/iris/backend/src/apps/market_data/services.py)

Assessment:

- dynamic continuous aggregate view reads and `refresh_continuous_aggregate` are acceptable documented exceptions because they are vendor-specific Timescale behavior.
- raw SQL should not spread beyond this infrastructure boundary.

### Logging Gap

Persistence operations currently lack a unified logger. There is no shared structured logging for:

- repository/query entry points
- transaction begin/commit/rollback
- raw SQL fallback/exception paths
- lock/select-for-update flows
- expensive read paths

Required action:

- introduce a shared persistence logger under `core/db`.

## Migration Order

Recommended rollout order:

1. shared persistence foundation in `core/db`
2. `apps/hypothesis_engine`
3. `apps/control_plane`
4. `apps/news`
5. `apps/market_structure`
6. `apps/market_data`
7. sync-heavy analytical domains (`indicators`, `patterns`, `signals`, `portfolio`, `predictions`, `cross_market`)

## Current Behavior To Preserve

- all existing HTTP routes and payload shapes must remain backward-compatible during migration.
- background workers and scheduled jobs must continue to use the same event types and Redis side effects.
- Timescale aggregate refresh behavior in `market_data` must remain semantically identical.
- control-plane topology publish/draft behavior must remain unchanged.
- hypothesis prompt caching and invalidation semantics must remain unchanged.
- news and market-structure source provisioning flows must remain unchanged for the frontend.
