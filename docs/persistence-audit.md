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

Status: migrated on the API/application surface

- Existing repositories are present in [backend/src/apps/control_plane/repositories.py](backend/src/apps/control_plane/repositories.py).
- Queries now flow through dedicated read services in [backend/src/apps/control_plane/query_services.py](backend/src/apps/control_plane/query_services.py).
- Views now depend on `get_uow()` and no longer take `AsyncSession` directly for caller-facing reads or writes.
- Read paths now return immutable dataclass models from [backend/src/apps/control_plane/read_models.py](backend/src/apps/control_plane/read_models.py), with explicit thawing only at transport/write boundaries.
- Route and draft mutation services now commit/flush via the shared UoW instead of direct session ownership.
- Structured persistence logging now covers control-plane repositories, query services and transaction lifecycle events.
- Remaining follow-up:
  - [backend/src/apps/control_plane/cache.py](backend/src/apps/control_plane/cache.py) still uses its own infrastructure-local session adapter, which is acceptable for now but should eventually adopt the same logging helpers.

Classification:

- `OK`

#### `apps/anomalies`

Status: migrated on the background/runtime surface

- repositories are centralized in [backend/src/apps/anomalies/repos/anomaly_repo.py](backend/src/apps/anomalies/repos/anomaly_repo.py)
- read-only anomaly list/detail flows now go through [backend/src/apps/anomalies/query_services.py](backend/src/apps/anomalies/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/anomalies/read_models.py](backend/src/apps/anomalies/read_models.py)
- the compatibility selector module now delegates to the query service instead of issuing ad-hoc session queries directly
- `candle_closed` consumers and anomaly enrichment / sector-scan tasks now own persistence through the shared async UoW instead of raw session commits
- persistence logging now covers anomaly repositories, query services, service orchestration and transaction lifecycle events
- sector and related-peer candle loading now batches peer reads in one explicit query path, removing the old loop-driven N+1 pattern from sector scan context building

Classification:

- `OK`

#### `apps/hypothesis_engine`

Status: migrated on the API/application surface and background entrypoints

- repositories are centralized in [backend/src/apps/hypothesis_engine/repositories.py](backend/src/apps/hypothesis_engine/repositories.py)
- read flows now go through [backend/src/apps/hypothesis_engine/query_services.py](backend/src/apps/hypothesis_engine/query_services.py)
- views, tasks and consumers now coordinate persistence through the shared async UoW
- read paths default to immutable dataclass models from [backend/src/apps/hypothesis_engine/read_models.py](backend/src/apps/hypothesis_engine/read_models.py)
- persistence logging covers repository, query and transaction events

Classification:

- `OK`

#### `apps/news`

Status: migrated on the API/application surface and background entrypoints

- repositories are isolated in [backend/src/apps/news/repositories.py](backend/src/apps/news/repositories.py)
- read-only list/detail flows now go through [backend/src/apps/news/query_services.py](backend/src/apps/news/query_services.py)
- immutable read models live in [backend/src/apps/news/read_models.py](backend/src/apps/news/read_models.py)
- source CRUD, polling, normalization and correlation now use the shared async UoW instead of direct session commits
- views, tasks and stream consumers no longer own raw `AsyncSession` boundaries directly
- list-item reads explicitly eager-load `links`, eliminating caller-side lazy loading on the public read path

Classification:

- `OK`

### Async Domains with Direct Persistence in Services

#### `apps/market_structure`

Status: migrated on the API/application surface and scheduled entrypoints

- repositories now isolate source locking, coin resolution and Core snapshot upserts in [backend/src/apps/market_structure/repositories.py](backend/src/apps/market_structure/repositories.py)
- read-only plugin/source/health/snapshot/webhook flows now go through [backend/src/apps/market_structure/query_services.py](backend/src/apps/market_structure/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/market_structure/read_models.py](backend/src/apps/market_structure/read_models.py)
- views and tasks now depend on the shared async UoW instead of owning `AsyncSession` directly
- source CRUD, polling, manual ingest, webhook ingest and provisioning flows now commit through the shared UoW and repositories instead of direct session commits
- snapshot persistence stays on SQLAlchemy Core upsert, but is now isolated behind a repository and logged as an explicit bulk/Core write path

Classification:

- `OK`

#### `apps/market_data`

Status: migrated on the async API/application surface and scheduled entrypoints

- repositories now isolate mutable coin/candle writes, metrics maintenance, delete cascades and Timescale aggregate refresh calls in [backend/src/apps/market_data/repositories.py](backend/src/apps/market_data/repositories.py)
- read-only coin/history/backfill candidate flows now go through [backend/src/apps/market_data/query_services.py](backend/src/apps/market_data/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/market_data/read_models.py](backend/src/apps/market_data/read_models.py)
- async CRUD/history sync orchestration now lives behind class-based services in [backend/src/apps/market_data/services.py](backend/src/apps/market_data/services.py)
- views and TaskIQ jobs now depend on the shared async UoW instead of owning `AsyncSession` / `AsyncSessionLocal` directly
- query-service backfill/latest-sync selection batches latest-candle lookups, removing caller-side N+1 checks from the public async path
- legacy sync adapters in [backend/src/apps/market_data/service_layer.py](backend/src/apps/market_data/service_layer.py) and [backend/src/apps/market_data/repos.py](backend/src/apps/market_data/repos.py) remain temporarily for sync-heavy analytical callers and Timescale-specific aggregate/resampling paths

Classification:

- `OK` on async/public callers
- `keep as justified raw SQL exception` for Timescale continuous aggregate refresh and dynamic aggregate-view reads/resampling in the legacy sync adapters
- `later migration` for sync-heavy analytical callers still consuming the legacy sync service layer

#### `apps/indicators`

Status: migrated on the async API/application surface and indicator worker path

- repositories now isolate mutable indicator metrics/cache/signals/feature-snapshot writes plus feature-flag lookups and candle/aggregate reads in [backend/src/apps/indicators/repositories.py](backend/src/apps/indicators/repositories.py)
- read-only metrics/radar/flow projections now go through [backend/src/apps/indicators/query_services.py](backend/src/apps/indicators/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/indicators/read_models.py](backend/src/apps/indicators/read_models.py)
- class-based async write orchestration now lives in [backend/src/apps/indicators/services.py](backend/src/apps/indicators/services.py)
- views now depend on the shared async UoW instead of owning `AsyncSession` directly
- `indicator_workers` now execute indicator persistence through async repositories/UoW instead of `AsyncSession.run_sync`
- market-radar/flow leader reads batch coin+metrics lookups, removing the old leader-path N+1 follow-up reads
- legacy sync analytical helpers were reduced to pure computation only in [backend/src/apps/indicators/analytics.py](backend/src/apps/indicators/analytics.py); DB access no longer lives there

Classification:

- `OK`

#### `apps/patterns`

Status: migrated on the async API/application and TaskIQ orchestration surface; legacy sync helper modules still remain under `domain/`

- repositories now isolate pattern feature and pattern registry write paths in [backend/src/apps/patterns/repositories.py](backend/src/apps/patterns/repositories.py)
- read-only pattern catalog, discovered pattern, coin regime, coin pattern, sector metrics and market-cycle projections now go through [backend/src/apps/patterns/query_services.py](backend/src/apps/patterns/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/patterns/read_models.py](backend/src/apps/patterns/read_models.py)
- views now depend on the shared async UoW instead of owning `AsyncSession` directly
- the market-cycle endpoint consumed by `indicators` now reuses the same query service instead of a module-level function facade
- persistence logging now covers pattern feature/pattern registry writes and public query paths
- TaskIQ flows now run through async class-based services in [backend/src/apps/patterns/task_services.py](backend/src/apps/patterns/task_services.py) and [backend/src/apps/patterns/tasks.py](backend/src/apps/patterns/tasks.py), removing the old `AsyncSession.run_sync` bridge from active runtime orchestration
- async market-data candle repositories now expose range/series fetchers used by the pattern task services without pushing raw session access back into the task layer
- remaining follow-up:
  - legacy sync modules under [backend/src/apps/patterns/domain](backend/src/apps/patterns/domain) still exist for compatibility/tests and should be retired incrementally as their async service equivalents absorb more helper logic
  - `signals` and `portfolio` still keep sync-heavy analytical selectors/services outside this migration slice

Classification:

- `OK` on async/public callers and TaskIQ entrypoints
- `later migration` for residual sync helper modules kept behind the persistence layer

#### `apps/cross_market`

Status: migrated on the async runtime/worker surface; legacy sync helpers remain for compatibility callers

- repositories now isolate Core upserts for `coin_relations` and `sector_metrics` in [backend/src/apps/cross_market/repositories.py](backend/src/apps/cross_market/repositories.py)
- read-only computation contexts now go through [backend/src/apps/cross_market/query_services.py](backend/src/apps/cross_market/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/cross_market/read_models.py](backend/src/apps/cross_market/read_models.py)
- active worker writes now run through [backend/src/apps/cross_market/services.py](backend/src/apps/cross_market/services.py) under the shared async UoW instead of `AsyncSession.run_sync`
- leader/follower candle loading now batches candidate leader history through [backend/src/apps/market_data/repositories.py](backend/src/apps/market_data/repositories.py), removing the old loop-driven N+1 path from relation updates
- correlation cache writes, prediction cache writes and emitted leader/rotation/correlation events now happen only after the persistence transaction commits on the active runtime path
- remaining follow-up:
  - legacy sync helpers under [backend/src/apps/cross_market/engine.py](backend/src/apps/cross_market/engine.py) still exist for `signals`/compatibility callers and should be retired incrementally as those callers migrate

Classification:

- `OK` on the async/background runtime surface
- `later migration` for residual sync helper callers kept behind the compatibility engine module

#### `apps/predictions`

Status: migrated on the async API surface, scheduled evaluation job and cross-market leader path; legacy sync helpers still remain for compatibility callers/tests

- repositories now isolate prediction candidate selection, pending-window checks and explicit relation-feedback locks in [backend/src/apps/predictions/repositories.py](backend/src/apps/predictions/repositories.py)
- read-only prediction list/detail flows now go through [backend/src/apps/predictions/query_services.py](backend/src/apps/predictions/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/predictions/read_models.py](backend/src/apps/predictions/read_models.py)
- API reads now depend on the shared async UoW instead of injecting `AsyncSession` directly in [backend/src/apps/predictions/views.py](backend/src/apps/predictions/views.py)
- scheduled evaluation now runs through [backend/src/apps/predictions/services.py](backend/src/apps/predictions/services.py) under the shared async UoW, with cache writes and published events deferred until after commit
- cross-market leader detection now calls the same class-based prediction service instead of issuing direct prediction writes through a module-level async helper
- creation now batches pending-window lookups by leader/target set, removing the old per-relation pending-check N+1 path from the active async flow
- remaining follow-up:
  - legacy sync helpers in [backend/src/apps/predictions/engine.py](backend/src/apps/predictions/engine.py) and [backend/src/apps/predictions/selectors.py](backend/src/apps/predictions/selectors.py) still exist for compatibility callers/tests and should be retired incrementally as the remaining sync-heavy domains migrate

Classification:

- `OK` on the async/public API and scheduled runtime surface
- `later migration` for residual sync helper callers kept behind the compatibility engine/selector modules

#### `apps/signals`

Status: migrated on the async/public API read surface and signal-fusion worker/runtime surface; residual sync history/backtests/strategy helpers still remain

- read-only signal, decision, market-decision, final-signal, backtest and strategy projections now go through [backend/src/apps/signals/query_services.py](backend/src/apps/signals/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/signals/read_models.py](backend/src/apps/signals/read_models.py)
- views now depend on the shared async UoW instead of injecting `AsyncSession` directly in [backend/src/apps/signals/views.py](backend/src/apps/signals/views.py)
- write-side signal-fusion persistence now goes through [backend/src/apps/signals/repositories.py](backend/src/apps/signals/repositories.py)
- [backend/src/apps/signals/services.py](backend/src/apps/signals/services.py) now hosts the class-based async `SignalFusionService` and post-commit side-effect dispatcher while preserving only sync compatibility exports for legacy callers
- [backend/src/runtime/streams/workers.py](backend/src/runtime/streams/workers.py) now routes `signal_fusion_workers` through the shared async UoW instead of opening sync write boundaries inside `fusion.py`
- market-decision detail reads keep their cache-first behavior but the fallback and DB projection are now logged through the shared persistence logger inside `SignalQueryService`
- remaining follow-up:
  - legacy sync compatibility helpers inside [backend/src/apps/signals/fusion.py](backend/src/apps/signals/fusion.py) still remain and should be retired once all remaining callers move to `SignalFusionService`
  - [backend/src/apps/signals/history.py](backend/src/apps/signals/history.py), [backend/src/apps/signals/backtests.py](backend/src/apps/signals/backtests.py) and [backend/src/apps/signals/strategies.py](backend/src/apps/signals/strategies.py) still own sync analytical logic and write boundaries that require a later async/class-first pass

Classification:

- `OK` on the async/public API read surface and active signal-fusion runtime surface
- `later migration` for residual sync analytical engines and write paths

#### `apps/portfolio`

Status: migrated on the async/public API read surface and scheduled balance-sync path; legacy sync engine/selectors still remain for compatibility callers/tests

- read-only portfolio projections now go through [backend/src/apps/portfolio/query_services.py](backend/src/apps/portfolio/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/portfolio/read_models.py](backend/src/apps/portfolio/read_models.py)
- write-side balance/account/state persistence now goes through [backend/src/apps/portfolio/repositories.py](backend/src/apps/portfolio/repositories.py)
- `/portfolio/*` views now depend on the shared async UoW instead of injecting `AsyncSession` directly in [backend/src/apps/portfolio/views.py](backend/src/apps/portfolio/views.py)
- `portfolio_sync_job` now runs through [backend/src/apps/portfolio/services.py](backend/src/apps/portfolio/services.py) under the shared async UoW, with cache writes and published events deferred until after commit
- the active sync path no longer re-fetches `ExchangeAccount` per balance row, removing an avoidable per-item read on the balance-sync loop
- remaining follow-up:
  - [backend/src/apps/portfolio/engine.py](backend/src/apps/portfolio/engine.py) and [backend/src/apps/portfolio/selectors.py](backend/src/apps/portfolio/selectors.py) still own sync analytical logic, ad-hoc dict read contracts and direct commit boundaries that require a later async/class-first pass

Classification:

- `OK` on the async/public API and scheduled sync surface
- `later migration` for residual sync analytical helpers kept behind the compatibility engine/selector modules

### Sync-Heavy Analytical Domains

These domains are still dominated by synchronous `Session` access inside selectors/engines and represent the largest remaining migration surface:

- residual sync analytical modules inside `apps/signals`
- legacy `apps/portfolio/engine.py` and `apps/portfolio/selectors.py`

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

Direct session injection on migrated FastAPI surfaces has been removed. Remaining DB-bound caller drift is concentrated in legacy sync analytical helpers rather than `views.py`.

### Transaction Boundary Drift

Representative offenders:

- [backend/src/apps/market_structure/services.py](backend/src/apps/market_structure/services.py)
- [backend/src/apps/market_data/services.py](backend/src/apps/market_data/services.py)
- [backend/src/apps/patterns/selectors.py](backend/src/apps/patterns/selectors.py)
- [backend/src/apps/portfolio/engine.py](backend/src/apps/portfolio/engine.py)

Required action:

- repositories may `flush()` when required for generated IDs or lock sequencing.
- application services / workers / tasks must own `commit()` and `rollback()`.
- query services must never commit.

### ORM Leakage and Untyped Read Contracts

Representative offenders:

- `market_data` still serializes ORM-backed state inside service/view logic.
- selectors in `patterns`, `signals`, and `portfolio` return `dict[str, Any]`.

Required action:

- default read contract becomes immutable dataclass read models.
- mutable ORM access must be explicit via write-side repository methods such as `get_for_update(...)`.

### Raw SQL Status

Current raw SQL outside migrations is concentrated in:

- [backend/src/apps/market_data/repos.py](backend/src/apps/market_data/repos.py)
- [backend/src/apps/market_data/services.py](backend/src/apps/market_data/services.py)

Assessment:

- dynamic continuous aggregate view reads and `refresh_continuous_aggregate` are acceptable documented exceptions because they are vendor-specific Timescale behavior.
- raw SQL should not spread beyond this infrastructure boundary.

### Logging Gap

Shared persistence logging now exists under `core/db` and is exercised in migrated domains. Remaining gaps are concentrated in unmigrated domains, where repository/query abstractions are still absent and DB access therefore bypasses the structured logger.

## Migration Order

Recommended rollout order:

1. completed: shared persistence foundation in `core/db`
2. completed: `apps/hypothesis_engine`
3. completed: `apps/control_plane`
4. completed: `apps/news`
5. completed: `apps/market_structure`
6. completed: `apps/anomalies`
7. completed: `apps/market_data`
8. completed: `apps/indicators`
9. completed on the async/public and TaskIQ orchestration surface: `apps/patterns`
10. completed on the async/background runtime surface: `apps/cross_market`
11. completed on the async/public API and scheduled runtime surface: `apps/predictions`
12. completed on the async/public API read and signal-fusion runtime surfaces: `apps/signals`
13. completed on the async/public API and scheduled sync surface: `apps/portfolio`
14. next: residual sync analytical helpers in `signals`
15. later: compatibility helpers in `predictions`, `cross_market`, `patterns` and legacy sync `portfolio` engine/selectors

## Current Behavior To Preserve

- all existing HTTP routes and payload shapes must remain backward-compatible during migration.
- background workers and scheduled jobs must continue to use the same event types and Redis side effects.
- Timescale aggregate refresh behavior in `market_data` must remain semantically identical.
- control-plane topology publish/draft behavior must remain unchanged.
- hypothesis prompt caching and invalidation semantics must remain unchanged.
- news and market-structure source provisioning flows must remain unchanged for the frontend.
