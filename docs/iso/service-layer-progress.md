# IRIS Service And Analytical Engine Refactor Progress

## Overall Status

- `service governance design`: done
- `analytical engine governance design`: done
- `direct final-form cutover strategy`: done
- `architecture CI policy scope`: done
- `reference module strategy`: done
- `semantic/operational/performance contract scope`: done
- `architecture CI implementation`: done
- `reference module implementation`: done
- `scorecard automation`: done
- `ADR package`: done
- `service hotspot clean rewrites`: done

## Non-Negotiable Constraints

- already standardized outer-layer contracts stay stable
- no interim compatibility stages inside service layer
- each hotspot is rewritten straight to final service/engine shape
- architecture rules must become CI gates, not markdown-only guidance

## Completed Blocks

- [x] Defined a unified service-layer governance standard
- [x] Defined a separate pure analytical engine standard for math-heavy domains
- [x] Locked `async-class-first` for orchestration and pure-function-first for analytical engines
- [x] Fixed the direct cutover rule: no staged service migrations
- [x] Defined the architecture CI policy scope
- [x] Selected `signals` as the canonical reference module
- [x] Added scorecard, ADR, explainability, reproducibility and operational requirements to the target standard

## Current Block

- [ ] Governance artifacts: idempotency/retry rules and performance budgets

## Active Workstreams

### 1. Architecture Enforcement

- [x] add `backend/tests/architecture/test_engine_purity.py`
- [x] add `backend/tests/architecture/test_service_result_contracts.py`
- [x] add `backend/tests/architecture/test_service_constructor_dependencies.py`
- [x] add `backend/tests/architecture/test_service_module_thresholds.py`
- [x] add `backend/tests/architecture/test_transport_leakage.py`
- [x] add `backend/tests/architecture/test_cross_domain_boundaries.py`
- [x] make these checks blocking in CI

### 2. Canonical Clean Rewrite: `signals`

- [x] split `backend/src/apps/signals/services.py` into `services/`
- [x] create `backend/src/apps/signals/engines/`
- [x] move fusion/history analytical logic to typed engine contracts
- [x] remove summary-shaped public service contracts
- [x] introduce explicit side-effect dispatcher boundary
- [x] add typed explainability contract
- [x] add engine tests without DB/runtime wiring
- [x] keep service tests focused on wiring, invariants and post-commit behavior
- [x] add a short ADR for the canonical module

### 3. Direct Hotspot Cutovers

- [x] Wave 2A: `predictions`
- [x] Wave 2B: `cross_market`
- [x] Wave 2C: `control_plane`
- [x] Wave 2D: `market_structure`
- [x] Wave 2E: `patterns/task_service_runtime`
- [x] Wave 2F: `anomalies`
- [x] Wave 3A: `market_data`
- [x] Wave 3B: `news`
- [x] Wave 3C: `indicators`
- [x] Wave 3D: `portfolio`

Правило для каждой rewrite-задачи:

- one domain rewrite = one final-form cutover
- no stop at temporary `dict/status` compatibility
- no stop at temporary giant-module split without final contracts
- no `AsyncSession`/transport leak carried forward “до следующего этапа”

### 4. Governance Artifacts

- [x] generate architecture scorecard from codebase facts
- [x] publish scorecard as CI artifact
- [x] add ADRs for transaction boundary, engine IO boundary, transport shaping, async-class-first scope and post-commit side effects
- [ ] define per-domain idempotency/retry/concurrency rules where background orchestration exists
- [ ] define per-domain performance budgets for heavy sync/job paths

## Cutover Order

### Wave 1

- `signals`

Цель:

- собрать канонический service/engine module, который копируется в остальные домены

### Wave 2

- `market_structure`
- `control_plane`
- `cross_market`
- `predictions`
- `patterns/task_service_runtime`
- `anomalies`

Цель:

- закрыть главные structural hotspots и math-heavy domains сразу в финальной форме

### Wave 3

- `market_data`
- `news`
- `indicators`
- `portfolio`

Цель:

- убрать оставшиеся session/payload/provider leaks и довести service layer до полного стандарта

## Progress Definition

План считается выполненным только если:

- architecture policy tests реально валят CI при нарушении стандарта
- `signals` существует как canonical reference module
- hot domains rewritten directly to final shape
- `dict[str, object]` / `{"status": ...}` public service contracts eliminated
- `AsyncSession` removed from service constructors/public helpers
- service layer no longer imports transport DTO
- side effects sit behind explicit post-commit boundaries
- semantic invariants, explainability, reproducibility and reentrancy are covered by tests
- no service rewrite leaves temporary compatibility stages behind

## Recent Progress

- [x] Stage 1 complete on `2026-03-14`: architecture governance baseline added under `backend/tests/architecture/` and wired into CI via `.github/workflows/architecture-governance.yml`
- [x] Stage 1 verification: `cd backend && uv run pytest tests/architecture`
- [x] Stage 2 complete on `2026-03-14`: `signals` moved to canonical `services/` + `engines/` shape, `services.py` removed, typed explainability/result contracts landed, and the cross-domain market-data repository shortcut moved behind an explicit adapter
- [x] Stage 2 verification: `cd backend && uv run pytest tests/apps/signals tests/architecture`
- [x] Stage 2 lint gate: `cd backend && uv run ruff check src/apps/signals/engines src/apps/signals/integrations src/apps/signals/services tests/apps/signals/test_fusion_branches.py tests/apps/signals/test_fusion_engine.py tests/apps/signals/test_history.py tests/apps/signals/test_history_engine.py tests/cross_market_support.py src/apps/patterns/task_service_history.py tests/architecture`
- [x] Stage 3 complete on `2026-03-14`: `predictions` moved from a single `services.py` module to `services/` + `engines/` + `integrations/`, prediction window evaluation became a pure engine contract, and `to_summary()` helpers were removed from public service results
- [x] Stage 3 verification: `cd backend && uv run pytest tests/apps/predictions tests/architecture`
- [x] Stage 3 lint gate: `cd backend && uv run ruff check src/apps/predictions/engines/__init__.py src/apps/predictions/engines/contracts.py src/apps/predictions/engines/window_engine.py src/apps/predictions/integrations/market_data.py src/apps/predictions/services/__init__.py src/apps/predictions/services/results.py src/apps/predictions/services/side_effects.py src/apps/predictions/services/prediction_service.py src/apps/predictions/tasks.py src/apps/cross_market/services.py tests/apps/predictions/test_window_engine.py tests/architecture/service_layer_baseline.py`
- [x] Stage 4 complete on `2026-03-14`: `cross_market` moved to `services/` + `engines/` + `integrations/`, correlation/sector/leader computations were separated from orchestration, public service contracts became typed results, and the direct market-data repository shortcut left the service layer
- [x] Stage 4 verification: `cd backend && uv run pytest tests/apps/cross_market tests/runtime/streams/test_workers.py tests/architecture`
- [x] Stage 4 lint gate: `cd backend && uv run ruff check src/apps/cross_market/engines src/apps/cross_market/integrations src/apps/cross_market/services src/apps/cross_market/support.py src/apps/signals/services/__init__.py src/apps/signals/services/fusion_helpers.py src/apps/signals/services/fusion_service.py tests/apps/cross_market tests/cross_market_support.py tests/architecture/service_layer_baseline.py`
- [x] Stage 5 complete on `2026-03-14`: `control_plane` moved from a single `services.py` module to `services/` + `engines/`, route snapshot/draft diff logic became pure engine code, and inline control-event publication left the service body for an explicit dispatcher
- [x] Stage 5 verification: `cd backend && uv run pytest tests/apps/control_plane tests/runtime/control_plane tests/architecture`
- [x] Stage 5 lint gate: `cd backend && uv run ruff check src/apps/control_plane/__init__.py src/apps/control_plane/api/presenters.py src/apps/control_plane/engines src/apps/control_plane/query_services.py src/apps/control_plane/services tests/apps/control_plane/test_engines.py tests/apps/control_plane/test_services.py tests/architecture/service_layer_baseline.py`
- [x] Stage 6 complete on `2026-03-14`: `market_structure` moved from a giant `services.py` module to `services/` + `engines/`, health/backoff/quarantine rules became pure engine code, typed polling/ingest results replaced `dict/status` contracts, and onboarding wizard transport shaping left the service layer for an API helper
- [x] Stage 6 verification: `cd backend && uv run pytest tests/apps/market_structure tests/architecture`
- [x] Stage 6 lint gate: `cd backend && uv run ruff check src/apps/market_structure/contracts.py src/apps/market_structure/schemas.py src/apps/market_structure/read_models.py src/apps/market_structure/tasks.py src/apps/market_structure/api/errors.py src/apps/market_structure/api/onboarding_endpoints.py src/apps/market_structure/api/onboarding_wizard.py src/apps/market_structure/api/presenters.py src/apps/market_structure/api/webhook_endpoints.py src/apps/market_structure/engines/__init__.py src/apps/market_structure/engines/health_engine.py src/apps/market_structure/services/__init__.py src/apps/market_structure/services/_shared.py src/apps/market_structure/services/market_structure_service.py src/apps/market_structure/services/polling_service.py src/apps/market_structure/services/provisioning_service.py src/apps/market_structure/services/results.py src/apps/market_structure/services/side_effects.py src/apps/market_structure/services/source_command_service.py tests/apps/market_structure/test_services.py tests/apps/market_structure/test_persistence_contracts.py tests/apps/market_structure/test_health_engine.py`
- [x] Stage 7 complete on `2026-03-14`: `patterns/task_service_runtime` now delegates cluster, hierarchy and cycle calculations to pure runtime engines/support modules, public realtime methods return typed results, and runtime workers consume attribute-based contracts instead of dict payloads
- [x] Stage 7 verification: `cd backend && uv run pytest tests/apps/patterns/test_realtime_engine.py tests/apps/patterns/test_services_async.py tests/runtime/streams/test_workers.py tests/architecture`
- [x] Stage 7 lint gate: `cd backend && uv run ruff check src/apps/patterns/query_services.py src/apps/patterns/repositories.py src/apps/patterns/runtime_results.py src/apps/patterns/runtime_steps.py src/apps/patterns/runtime_support.py src/apps/patterns/task_service_runtime.py src/runtime/streams/workers.py tests/apps/patterns/test_realtime_engine.py tests/apps/patterns/test_services_async.py tests/runtime/streams/test_workers.py tests/architecture/service_layer_baseline.py`
- [x] Stage 8 complete on `2026-03-14`: `anomalies` moved off dict-shaped service contracts, anomaly domain contracts left `schemas.py`, and anomaly payload/enrichment shaping left `anomaly_service.py` for dedicated engine/support modules
- [x] Stage 8 verification: `cd backend && uv run pytest tests/apps/anomalies/test_payload_engine.py tests/apps/anomalies/test_persistence_contracts.py tests/architecture`
- [x] Stage 8 lint gate: `cd backend && uv run ruff check src/apps/anomalies/contracts.py src/apps/anomalies/schemas.py src/apps/anomalies/engines src/apps/anomalies/results.py src/apps/anomalies/detection_runner.py src/apps/anomalies/services/anomaly_service.py src/apps/anomalies/tasks/anomaly_enrichment_tasks.py tests/apps/anomalies/test_payload_engine.py tests/apps/anomalies/test_persistence_contracts.py tests/architecture/service_layer_baseline.py`
- [x] Stage 9 complete on `2026-03-14`: `market_data` now keeps public services typed, sync task payload shaping at the task boundary, and operational write/history helpers extracted out of `services.py` so the service module no longer mixes transport DTOs, dict contracts and giant write-side orchestration
- [x] Stage 9 verification: `cd backend && uv run pytest tests/apps/market_data/test_services.py tests/apps/market_data/test_tasks.py tests/apps/market_data/test_persistence_contracts.py tests/architecture`
- [x] Stage 9 lint gate: `cd backend && uv run ruff check src/apps/market_data/command_support.py src/apps/market_data/contracts.py src/apps/market_data/history_sync.py src/apps/market_data/results.py src/apps/market_data/services.py src/apps/market_data/tasks.py tests/apps/market_data/test_services.py tests/apps/market_data/test_tasks.py tests/apps/market_data/test_persistence_contracts.py tests/architecture/service_layer_baseline.py`
- [x] Stage 10 complete on `2026-03-14`: `news` no longer keeps polling, telegram onboarding and telegram provisioning in one hotspot; public poll methods now return typed results, telegram wizard routing left the service layer, and `news/services.py` is reduced to a small facade over focused modules
- [x] Stage 10 verification: `cd backend && uv run pytest tests/apps/news/test_services.py tests/apps/news/test_views.py tests/apps/news/test_pipeline.py tests/apps/news/test_persistence_contracts.py tests/architecture`
- [x] Stage 10 lint gate: `cd backend && uv run ruff check src/apps/news/contracts.py src/apps/news/results.py src/apps/news/polling.py src/apps/news/telegram_onboarding.py src/apps/news/telegram_provisioning.py src/apps/news/services.py src/apps/news/schemas.py src/apps/news/tasks.py src/apps/news/api/onboarding_endpoints.py src/apps/news/api/onboarding_wizard.py tests/apps/news/test_services.py tests/architecture/service_layer_baseline.py`
- [x] Stage 11 complete on `2026-03-14`: `indicators` no longer keeps analytics, snapshot capture and scheduling in one service hotspot; analytics stays test-seam compatible in `services.py`, while snapshot/scheduler/results/support moved to focused modules and direct market-data model/repository imports left the service file
- [x] Stage 11 verification: `cd backend && uv run pytest tests/apps/indicators/test_analytics_helpers.py tests/apps/indicators/test_flow_radar_snapshots_services.py tests/apps/indicators/test_persistence_contracts.py tests/architecture`
- [x] Stage 11 lint gate: `cd backend && uv run ruff check src/apps/indicators/results.py src/apps/indicators/service_support.py src/apps/indicators/feature_snapshot_service.py src/apps/indicators/analysis_scheduler_service.py src/apps/indicators/services.py src/apps/indicators/snapshots.py tests/apps/indicators/test_analytics_helpers.py tests/apps/indicators/test_flow_radar_snapshots_services.py tests/apps/indicators/test_persistence_contracts.py tests/architecture/service_layer_baseline.py`
- [x] Stage 12 complete on `2026-03-14`: `portfolio` no longer exposes payload summary helpers on public result contracts, pure rebalance calculation moved into `engines/`, balance/action orchestration moved to focused support modules, and `portfolio/services.py` no longer imports market-data/signals models or repositories directly
- [x] Stage 12 verification: `cd backend && uv run pytest tests/apps/portfolio tests/architecture`
- [x] Stage 12 lint gate: `cd backend && uv run ruff check src/apps/portfolio/action_support.py src/apps/portfolio/results.py src/apps/portfolio/serializers.py src/apps/portfolio/services.py src/apps/portfolio/sync_support.py src/apps/portfolio/tasks.py src/apps/portfolio/engines tests/apps/portfolio/test_rebalance_engine.py tests/apps/portfolio/test_services_selectors_cache.py tests/architecture/service_layer_baseline.py`
- [x] Stage 13 complete on `2026-03-14`: service-layer scorecard generation now reuses the architecture policy scanners, exports Markdown/JSON snapshots, and the architecture workflow uploads them as CI artifacts
- [x] Stage 13 verification: `cd backend && uv run pytest tests/architecture`
- [x] Stage 13 artifact export: `cd backend && uv run python scripts/export_service_layer_scorecard.py --markdown-output /tmp/service-layer-scorecard.md --json-output /tmp/service-layer-scorecard.json`
- [x] Stage 14 complete on `2026-03-14`: ADRs now document caller-owned commit, engine IO boundary, transport shaping, async orchestration scope and post-commit side effects; architecture policy and the canonical `signals` package reference the ADR package, and CI checks that the ADR set exists
- [x] Stage 14 verification: `cd backend && uv run pytest tests/architecture`
- [x] Stage 14 lint gate: `cd backend && uv run ruff check tests/architecture/service_layer_policy.py tests/architecture/test_service_layer_adrs.py src/apps/signals/services/__init__.py`
