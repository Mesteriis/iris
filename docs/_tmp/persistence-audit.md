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
- legacy Timescale adapters in [backend/src/apps/market_data/repos.py](backend/src/apps/market_data/repos.py) now degrade to structured warning logs plus direct/resampled candle fallback when continuous aggregate procedures or materialized views are unavailable, which keeps sync analytical callers/tests from failing hard on partial DB environments
- async candle bulk reads in [backend/src/apps/market_data/repositories.py](backend/src/apps/market_data/repositories.py) now keep partial aggregate-view failures on a batched path and return structured partial results instead of silently degrading into per-coin fallback reads, preserving the anti-N+1 contract consumed by `cross_market`
- sync and async candle resampling paths now fall back to in-process aggregation of base candle rows when Timescale `time_bucket`/`first`/`last` functions are unavailable, keeping read contracts stable on PostgreSQL-only test environments without reintroducing caller-side DB access
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
- aggregate availability checks in [backend/src/apps/indicators/repositories.py](backend/src/apps/indicators/repositories.py) and async refresh calls in [backend/src/apps/market_data/repositories.py](backend/src/apps/market_data/repositories.py) now degrade to structured warning logs plus direct/resampled candle fallback or skipped refreshes when Timescale views/procedures are unavailable, keeping worker pipelines alive on PostgreSQL-only test environments
- legacy sync analytical helpers were reduced to pure computation only in [backend/src/apps/indicators/analytics.py](backend/src/apps/indicators/analytics.py); DB access no longer lives there

Classification:

- `OK`

#### `apps/patterns`

Status: migrated on the async API/application, TaskIQ orchestration and runtime worker surfaces; legacy sync helper modules still remain under `domain/`

- repositories now isolate pattern feature and pattern registry write paths in [backend/src/apps/patterns/repositories.py](backend/src/apps/patterns/repositories.py)
- read-only pattern catalog, discovered pattern, coin regime, coin pattern, sector metrics and market-cycle projections now go through [backend/src/apps/patterns/query_services.py](backend/src/apps/patterns/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/patterns/read_models.py](backend/src/apps/patterns/read_models.py)
- views now depend on the shared async UoW instead of owning `AsyncSession` directly
- the market-cycle endpoint consumed by `indicators` now reuses the same query service instead of a module-level function facade
- async signal projection builders now live in [backend/src/apps/patterns/query_builders.py](backend/src/apps/patterns/query_builders.py) and are reused by both `patterns` and `signals` query services instead of importing selector helpers from [backend/src/apps/patterns/selectors.py](backend/src/apps/patterns/selectors.py)
- persistence logging now covers pattern feature/pattern registry writes and public query paths
- TaskIQ flows now run through async class-based services in [backend/src/apps/patterns/task_services.py](backend/src/apps/patterns/task_services.py) and [backend/src/apps/patterns/tasks.py](backend/src/apps/patterns/tasks.py), removing the old `AsyncSession.run_sync` bridge from active runtime orchestration
- `pattern_workers` and `regime_workers` now delegate incremental detection + regime refresh to async class-based [backend/src/apps/patterns/task_service_runtime.py](backend/src/apps/patterns/task_service_runtime.py) (`PatternRealtimeService`) under shared UoW ownership, removing the old sync `PatternEngine` / `update_market_cycle` / cluster+hierarchy `run_sync` path from [backend/src/runtime/streams/workers.py](backend/src/runtime/streams/workers.py)
- `decision_workers` now delegate context enrichment plus decision/final-signal generation to async `PatternSignalContextService` under UoW, removing the old sync `run_sync` decision path from [backend/src/runtime/streams/workers.py](backend/src/runtime/streams/workers.py)
- `PatternSignalContextService` now exposes `enrich_context_only(...)` from [backend/src/apps/patterns/task_services.py](backend/src/apps/patterns/task_services.py), so `signals` runtime callers can reuse async context enrichment without invoking the broader sync compatibility flow
- legacy sync selectors in [backend/src/apps/patterns/selectors.py](backend/src/apps/patterns/selectors.py) now emit structured deprecation logs and reuse the same shared signal projection builders plus immutable read-model mapping logic as [backend/src/apps/patterns/query_services.py](backend/src/apps/patterns/query_services.py)
- async and sync `list_coin_patterns` read paths now share the same explicit ordering profile from [backend/src/apps/patterns/query_builders.py](backend/src/apps/patterns/query_builders.py), preventing timestamp-tie instability between base pattern rows and derived cluster/hierarchy rows
- async regime cache clients in [backend/src/apps/patterns/cache.py](backend/src/apps/patterns/cache.py) are now loop-scoped instead of process-global cached clients
- async market-data candle repositories now expose range/series fetchers used by the pattern task services without pushing raw session access back into the task layer
- remaining follow-up:
  - legacy sync modules under [backend/src/apps/patterns/domain](backend/src/apps/patterns/domain) still exist for compatibility/tests and should be retired incrementally as their async service equivalents absorb more helper logic
  - [backend/src/apps/patterns/selectors.py](backend/src/apps/patterns/selectors.py) still owns sync write compatibility wrappers with direct `commit()` boundaries and should be retired once compatibility callers stop depending on the sync API

Classification:

- `OK` on async/public callers, TaskIQ entrypoints and runtime workers
- `later migration` for residual sync helper modules kept behind the persistence layer

#### `apps/cross_market`

Status: migrated on the async runtime/worker surface; legacy sync helpers remain for compatibility callers

- repositories now isolate Core upserts for `coin_relations` and `sector_metrics` in [backend/src/apps/cross_market/repositories.py](backend/src/apps/cross_market/repositories.py)
- read-only computation contexts now go through [backend/src/apps/cross_market/query_services.py](backend/src/apps/cross_market/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/cross_market/read_models.py](backend/src/apps/cross_market/read_models.py)
- active worker writes now run through [backend/src/apps/cross_market/services.py](backend/src/apps/cross_market/services.py) under the shared async UoW instead of `AsyncSession.run_sync`
- leader/follower candle loading now batches candidate leader history through [backend/src/apps/market_data/repositories.py](backend/src/apps/market_data/repositories.py), removing the old loop-driven N+1 path from relation updates
- correlation cache writes, prediction cache writes and emitted leader/rotation/correlation events now happen only after the persistence transaction commits on the active runtime path
- legacy sync helpers under [backend/src/apps/cross_market/engine.py](backend/src/apps/cross_market/engine.py) now emit structured deprecation logs and reuse the same summary result contracts as the async service layer, keeping compatibility callers on the same payload shape while migration continues
- async correlation cache clients in [backend/src/apps/cross_market/cache.py](backend/src/apps/cross_market/cache.py) are now loop-scoped like `signals`/`predictions`, removing another shared-client edge from tests and worker runtimes
- remaining follow-up:
  - legacy sync helpers under [backend/src/apps/cross_market/engine.py](backend/src/apps/cross_market/engine.py) still exist for `signals`/compatibility callers and should be retired incrementally as those callers migrate off the compatibility module entirely

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
- shared prediction constants/outcome helpers used by async services now live in [backend/src/apps/predictions/support.py](backend/src/apps/predictions/support.py), removing service-level imports from the legacy sync compatibility engine
- legacy sync helpers in [backend/src/apps/predictions/engine.py](backend/src/apps/predictions/engine.py) and [backend/src/apps/predictions/selectors.py](backend/src/apps/predictions/selectors.py) now emit structured deprecation logs, share a common prediction select builder and use the same summary/result contracts as the async service and query layers
- async prediction cache clients in [backend/src/apps/predictions/cache.py](backend/src/apps/predictions/cache.py) are now loop-scoped instead of process-global cached objects
- remaining follow-up:
  - legacy sync helpers in [backend/src/apps/predictions/engine.py](backend/src/apps/predictions/engine.py) and [backend/src/apps/predictions/selectors.py](backend/src/apps/predictions/selectors.py) still exist for compatibility callers/tests and should be retired incrementally as the remaining sync-heavy domains migrate

Classification:

- `OK` on the async/public API and scheduled runtime surface
- `later migration` for residual sync helper callers kept behind the compatibility engine/selector modules

#### `apps/signals`

Status: migrated on the async/public API read surface plus signal-fusion and signal-history runtime surfaces; residual sync backtests/strategy helpers still remain

- read-only signal, decision, market-decision, final-signal, backtest and strategy projections now go through [backend/src/apps/signals/query_services.py](backend/src/apps/signals/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/signals/read_models.py](backend/src/apps/signals/read_models.py)
- views now depend on the shared async UoW instead of injecting `AsyncSession` directly in [backend/src/apps/signals/views.py](backend/src/apps/signals/views.py)
- write-side signal-fusion persistence now goes through [backend/src/apps/signals/repositories.py](backend/src/apps/signals/repositories.py)
- history writes now also go through [backend/src/apps/signals/repositories.py](backend/src/apps/signals/repositories.py)
- [backend/src/apps/signals/services.py](backend/src/apps/signals/services.py) now hosts only class-based async `SignalFusionService`, `SignalHistoryService` and post-commit side-effect dispatchers on the active runtime path, without re-exporting legacy sync compatibility helpers
- [backend/src/runtime/streams/workers.py](backend/src/runtime/streams/workers.py) now routes `signal_fusion_workers` through the shared async UoW instead of opening sync write boundaries inside `fusion.py`
- [backend/src/runtime/streams/workers.py](backend/src/runtime/streams/workers.py) now refreshes signal history through the shared async UoW instead of calling `refresh_recent_signal_history()` inside the sync decision flow
- [backend/src/apps/patterns/task_service_history.py](backend/src/apps/patterns/task_service_history.py) now delegates signal-history refresh to `SignalHistoryService`, removing the duplicated async history persistence path
- active async query/service code now uses [backend/src/apps/signals/backtest_support.py](backend/src/apps/signals/backtest_support.py), [backend/src/apps/signals/fusion_support.py](backend/src/apps/signals/fusion_support.py) and [backend/src/apps/signals/history_support.py](backend/src/apps/signals/history_support.py) instead of importing pure helper logic from the legacy sync compatibility modules directly
- active async query paths now resolve latest decision/final-signal/market-decision ranking subqueries via [backend/src/apps/signals/query_builders.py](backend/src/apps/signals/query_builders.py), removing direct imports from compatibility selector modules inside [backend/src/apps/signals/query_services.py](backend/src/apps/signals/query_services.py)
- sync compatibility selector adapters now reuse the same latest-* query builders and align sector projection with the async read path, avoiding drift between `SignalQueryService` payloads and legacy selector payloads
- `SignalFusionService` now enriches pattern context through async [backend/src/apps/patterns/task_services.py](backend/src/apps/patterns/task_services.py) (`PatternSignalContextService.enrich_context_only`) under shared UoW ownership, removing the old `AsyncSession.run_sync` bridge to `patterns.domain.context`
- sync compatibility readers in [backend/src/apps/signals/backtests.py](backend/src/apps/signals/backtests.py), [backend/src/apps/signals/strategies.py](backend/src/apps/signals/strategies.py), [backend/src/apps/signals/decision_selectors.py](backend/src/apps/signals/decision_selectors.py), [backend/src/apps/signals/market_decision_selectors.py](backend/src/apps/signals/market_decision_selectors.py) and [backend/src/apps/signals/final_signal_selectors.py](backend/src/apps/signals/final_signal_selectors.py) now use class-based adapters with structured deprecation logs
- legacy sync `backtests.py` and `strategies.py` adapters now also normalize their public payloads through shared immutable [backend/src/apps/signals/read_models.py](backend/src/apps/signals/read_models.py) contracts instead of formatting transport dictionaries directly from ORM/query rows
- sync compatibility write entrypoints in [backend/src/apps/signals/fusion.py](backend/src/apps/signals/fusion.py) and [backend/src/apps/signals/history.py](backend/src/apps/signals/history.py) now run through class-based compatibility services with structured deprecation logs and emit the same summary-shape contracts as the active async services
- market-decision detail reads keep their cache-first behavior but the fallback and DB projection are now logged through the shared persistence logger inside `SignalQueryService`
- remaining follow-up:
  - legacy sync compatibility helpers inside [backend/src/apps/signals/fusion.py](backend/src/apps/signals/fusion.py) still remain and should be retired once all remaining callers move to `SignalFusionService`
  - legacy sync compatibility helpers inside [backend/src/apps/signals/history.py](backend/src/apps/signals/history.py) still remain and should be retired once all remaining callers move to `SignalHistoryService`
  - [backend/src/apps/signals/backtests.py](backend/src/apps/signals/backtests.py), [backend/src/apps/signals/strategies.py](backend/src/apps/signals/strategies.py), [backend/src/apps/signals/decision_selectors.py](backend/src/apps/signals/decision_selectors.py), [backend/src/apps/signals/market_decision_selectors.py](backend/src/apps/signals/market_decision_selectors.py) and [backend/src/apps/signals/final_signal_selectors.py](backend/src/apps/signals/final_signal_selectors.py) remain sync compatibility adapters and should eventually be removed in favor of `SignalQueryService`

Classification:

- `OK` on the async/public API read surface and active signal-fusion/signal-history runtime surfaces
- `later migration` for residual sync analytical engines and write paths

#### `apps/portfolio`

Status: migrated on the async/public API read surface, scheduled balance-sync path and runtime worker action path; legacy sync engine/selectors still remain for compatibility callers/tests

- read-only portfolio projections now go through [backend/src/apps/portfolio/query_services.py](backend/src/apps/portfolio/query_services.py)
- immutable dataclass read models now live in [backend/src/apps/portfolio/read_models.py](backend/src/apps/portfolio/read_models.py)
- write-side balance/account/state persistence now goes through [backend/src/apps/portfolio/repositories.py](backend/src/apps/portfolio/repositories.py)
- `/portfolio/*` views now depend on the shared async UoW instead of injecting `AsyncSession` directly in [backend/src/apps/portfolio/views.py](backend/src/apps/portfolio/views.py)
- `portfolio_sync_job` now runs through [backend/src/apps/portfolio/services.py](backend/src/apps/portfolio/services.py) under the shared async UoW, with cache writes and published events deferred until after commit
- `portfolio_workers` now evaluate portfolio actions through the class-based async `PortfolioService` under the shared async UoW, with event/cache side effects applied post-commit
- async portfolio decision-ranking projection now uses [backend/src/apps/portfolio/query_builders.py](backend/src/apps/portfolio/query_builders.py) from both query and compatibility selector layers, and shared position-sizing/stop helpers now live in [backend/src/apps/portfolio/support.py](backend/src/apps/portfolio/support.py) so async services no longer depend on legacy sync engine modules
- legacy sync selectors in [backend/src/apps/portfolio/selectors.py](backend/src/apps/portfolio/selectors.py) now emit structured deprecation logs and reuse the same shared projection builders plus immutable read-model mapping logic as [backend/src/apps/portfolio/query_services.py](backend/src/apps/portfolio/query_services.py)
- legacy sync wrappers in [backend/src/apps/portfolio/engine.py](backend/src/apps/portfolio/engine.py) now emit structured deprecation logs, normalize their public payloads through the same `PortfolioActionEvaluationResult` / `PortfolioSyncResult` summary contracts used by the async service layer, and own fewer ad-hoc commit boundaries on the action-evaluation path
- async portfolio cache clients in [backend/src/apps/portfolio/cache.py](backend/src/apps/portfolio/cache.py) are now loop-scoped instead of process-global cached clients
- the active sync path no longer re-fetches `ExchangeAccount` per balance row, removing an avoidable per-item read on the balance-sync loop
- sync balance compatibility coin creation in [backend/src/apps/portfolio/engine.py](backend/src/apps/portfolio/engine.py) now stays inside the portfolio persistence adapter instead of delegating to legacy [backend/src/apps/market_data/service_layer.py](backend/src/apps/market_data/service_layer.py), and it aligns default `Coin` / `CoinMetrics` initialization with the async service path
- sync balance compatibility events in [backend/src/apps/portfolio/engine.py](backend/src/apps/portfolio/engine.py) are now queued until after the balance-row commit instead of being published from nested helper-owned write paths, reducing another legacy transaction/side-effect interleave
- remaining follow-up:
  - [backend/src/apps/portfolio/engine.py](backend/src/apps/portfolio/engine.py) and [backend/src/apps/portfolio/selectors.py](backend/src/apps/portfolio/selectors.py) still own sync analytical logic plus the remaining balance-sync commit boundaries that require a later async/class-first retirement of the compatibility layer

Classification:

- `OK` on the async/public API, scheduled sync and runtime worker surfaces
- `later migration` for residual sync analytical helpers kept behind the compatibility engine/selector modules

### Sync-Heavy Analytical Domains

These domains are still dominated by synchronous `Session` access inside selectors/engines and represent the largest remaining migration surface:

- residual sync compatibility modules inside `apps/signals/backtests.py`, `apps/signals/strategies.py`, `apps/signals/fusion.py` and `apps/signals/history.py` (now class-based adapters/services, still sync contracts)
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

Runtime note:

- `analysis_scheduler_workers` now use `AnalysisSchedulerService` under shared async UoW ownership instead of direct `AsyncSession` reads/commits in [backend/src/runtime/streams/workers.py](backend/src/runtime/streams/workers.py).

### Transaction Boundary Drift

Representative offenders:

- [backend/src/apps/market_structure/services.py](backend/src/apps/market_structure/services.py)
- [backend/src/apps/market_data/services.py](backend/src/apps/market_data/services.py)
- [backend/src/apps/patterns/selectors.py](backend/src/apps/patterns/selectors.py)
- [backend/src/apps/portfolio/engine.py](backend/src/apps/portfolio/engine.py)

Recently fixed:

- analysis scheduler stream handling in [backend/src/runtime/streams/workers.py](backend/src/runtime/streams/workers.py) no longer commits through direct session ownership.

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
9. completed on the async/public, TaskIQ orchestration and runtime worker surfaces: `apps/patterns`
10. completed on the async/background runtime surface: `apps/cross_market`
11. completed on the async/public API and scheduled runtime surface: `apps/predictions`
12. completed on the async/public API read plus signal-fusion/signal-history runtime surfaces: `apps/signals`
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
