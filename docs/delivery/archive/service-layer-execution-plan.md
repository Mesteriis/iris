# IRIS Service Layer Execution Plan

> Historical execution plan.
> All listed stages are complete; keep this file only as rollout history.

## Source Of Truth

- audit standard: `docs/delivery/service-layer-refactor-audit.md`
- progress board: `docs/delivery/archive/service-layer-progress.md`

## Execution Rules

- one stage = one focused commit
- wave stages are split into per-domain cutovers when a single wave contains multiple hotspots
- each stage updates this tracker and the shared progress board
- stage commits include only files directly related to that stage
- no interim compatibility rewrites inside service layer

## Stage Board

### Stage 1. Architecture Governance Baseline

Status: done

Goal:

- stand up AST-based service-layer policy tests
- make the policy suite blocking in CI
- record the current known debt as an explicit baseline

Deliverables:

- [x] `backend/tests/architecture/test_engine_purity.py`
- [x] `backend/tests/architecture/test_service_result_contracts.py`
- [x] `backend/tests/architecture/test_service_constructor_dependencies.py`
- [x] `backend/tests/architecture/test_service_module_thresholds.py`
- [x] `backend/tests/architecture/test_transport_leakage.py`
- [x] `backend/tests/architecture/test_cross_domain_boundaries.py`
- [x] `backend/tests/architecture/service_layer_policy.py`
- [x] `backend/tests/architecture/service_layer_baseline.py`
- [x] `.github/workflows/architecture-governance.yml`

Verification:

- [x] `cd backend && uv run pytest tests/architecture`

### Stage 2. Canonical Rewrite: `signals`

Status: done

Goal:

- split `backend/src/apps/signals/services.py` into `services/`
- introduce `backend/src/apps/signals/engines/`
- remove summary-shaped contracts from public service results
- keep persistence and transport boundaries stable

Planned deliverables:

- [x] service package split
- [x] engine contracts and explainability contracts
- [x] engine unit tests without DB/runtime wiring
- [x] service tests focused on wiring and post-commit behavior
- [x] short ADR for the canonical module

Verification:

- [x] `cd backend && uv run pytest tests/apps/signals tests/architecture`
- [x] `cd backend && uv run ruff check src/apps/signals/engines src/apps/signals/integrations src/apps/signals/services tests/apps/signals/test_fusion_branches.py tests/apps/signals/test_fusion_engine.py tests/apps/signals/test_history.py tests/apps/signals/test_history_engine.py tests/cross_market_support.py src/apps/patterns/task_service_history.py tests/architecture`

### Stage 3. Wave 2A: `predictions`

Status: done

Goal:

- split `backend/src/apps/predictions/services.py` into `services/`
- introduce a pure prediction-window engine under `backend/src/apps/predictions/engines/`
- remove summary-shaped public prediction service contracts
- remove direct cross-domain market-data access from the service body

Planned deliverables:

- [x] service package split
- [x] prediction window engine contracts and pure evaluation function
- [x] explicit market-data adapter
- [x] task consumer updated to shape transport payload outside services
- [x] engine unit tests without DB/runtime wiring

Verification:

- [x] `cd backend && uv run pytest tests/apps/predictions tests/architecture`
- [x] `cd backend && uv run ruff check src/apps/predictions/engines/__init__.py src/apps/predictions/engines/contracts.py src/apps/predictions/engines/window_engine.py src/apps/predictions/integrations/market_data.py src/apps/predictions/services/__init__.py src/apps/predictions/services/results.py src/apps/predictions/services/side_effects.py src/apps/predictions/services/prediction_service.py src/apps/predictions/tasks.py src/apps/cross_market/services.py tests/apps/predictions/test_window_engine.py tests/architecture/service_layer_baseline.py`

### Stage 4. Wave 2B: `cross_market`

Status: done

Goal:

- split `backend/src/apps/cross_market/services.py` into `services/`
- move correlation, sector momentum and leader-threshold calculations into pure engines
- remove summary-shaped public service contracts
- remove direct market-data repository access from the service layer

Planned deliverables:

- [x] service package split
- [x] relation/sector/leader engines
- [x] explicit market-data adapter
- [x] typed process/result contracts without `to_summary()`
- [x] explicit cross-market side-effect dispatcher boundary
- [x] pure engine tests without DB/runtime wiring

Verification:

- [x] `cd backend && uv run pytest tests/apps/cross_market tests/runtime/streams/test_workers.py tests/architecture`
- [x] `cd backend && uv run ruff check src/apps/cross_market/engines src/apps/cross_market/integrations src/apps/cross_market/services src/apps/cross_market/support.py src/apps/signals/services/__init__.py src/apps/signals/services/fusion_helpers.py src/apps/signals/services/fusion_service.py tests/apps/cross_market tests/cross_market_support.py tests/architecture/service_layer_baseline.py`

### Stage 5. Wave 2C: `control_plane`

Status: done

Goal:

- split `backend/src/apps/control_plane/services.py` into `services/`
- move route snapshot shaping and topology draft diff preview into pure engines
- remove read-side service wrappers that leaked `AsyncSession` and dict-shaped payloads
- replace inline control-event/cache payload publication with an explicit dispatcher boundary

Planned deliverables:

- [x] service package split with focused command-service modules
- [x] route snapshot and topology diff engines
- [x] explicit control-plane side-effect dispatcher
- [x] shared route mutation writer for command/draft write paths
- [x] pure engine tests without DB/runtime wiring

Verification:

- [x] `cd backend && uv run pytest tests/apps/control_plane tests/runtime/control_plane tests/architecture`
- [x] `cd backend && uv run ruff check src/apps/control_plane/__init__.py src/apps/control_plane/api/presenters.py src/apps/control_plane/engines src/apps/control_plane/query_services.py src/apps/control_plane/services tests/apps/control_plane/test_engines.py tests/apps/control_plane/test_services.py tests/architecture/service_layer_baseline.py`

### Stage 6. Wave 2D: `market_structure`

Status: done

Goal:

- split `backend/src/apps/market_structure/services.py` into `services/`
- move health/backoff/quarantine state transitions into a pure engine
- remove `dict/status` public service contracts from polling and ingest flows
- keep onboarding transport shaping and TaskIQ payload shaping outside the service layer

Planned deliverables:

- [x] service package split with focused command/polling/provisioning services
- [x] pure `health_engine` for stale/backoff/quarantine/alert transitions
- [x] typed polling/ingest/health refresh result contracts
- [x] explicit post-commit side-effect dispatcher
- [x] onboarding wizard moved to API helper and service-layer transport leakage removed
- [x] pure engine tests without DB/runtime wiring

Verification:

- [x] `cd backend && uv run pytest tests/apps/market_structure tests/architecture`
- [x] `cd backend && uv run ruff check src/apps/market_structure/contracts.py src/apps/market_structure/schemas.py src/apps/market_structure/read_models.py src/apps/market_structure/tasks.py src/apps/market_structure/api/errors.py src/apps/market_structure/api/onboarding_endpoints.py src/apps/market_structure/api/onboarding_wizard.py src/apps/market_structure/api/presenters.py src/apps/market_structure/api/webhook_endpoints.py src/apps/market_structure/engines/__init__.py src/apps/market_structure/engines/health_engine.py src/apps/market_structure/services/__init__.py src/apps/market_structure/services/_shared.py src/apps/market_structure/services/market_structure_service.py src/apps/market_structure/services/polling_service.py src/apps/market_structure/services/provisioning_service.py src/apps/market_structure/services/results.py src/apps/market_structure/services/side_effects.py src/apps/market_structure/services/source_command_service.py tests/apps/market_structure/test_services.py tests/apps/market_structure/test_persistence_contracts.py tests/apps/market_structure/test_health_engine.py`

### Stage 7. Wave 2E: `patterns/task_service_runtime`

Status: done

Goal:

- split incremental runtime orchestration from pure pattern cluster/hierarchy/cycle calculations
- remove `dict/status` public realtime service contracts
- remove direct cross-domain model imports from `task_service_runtime.py`
- reduce the runtime hotspot below service-layer module/class thresholds

Planned deliverables:

- [x] pure realtime engine contracts and calculation helpers under `backend/src/apps/patterns/engines/`
- [x] typed runtime result contracts for detection and regime refresh
- [x] query/repository helpers for signal snapshots, metrics snapshots and cycle writes
- [x] worker consumers updated to attribute-based result handling
- [x] pure engine tests and runtime service tests aligned with final contracts

Verification:

- [x] `cd backend && uv run pytest tests/apps/patterns/test_realtime_engine.py tests/apps/patterns/test_services_async.py tests/runtime/streams/test_workers.py tests/architecture`
- [x] `cd backend && uv run ruff check src/apps/patterns/query_services.py src/apps/patterns/repositories.py src/apps/patterns/runtime_results.py src/apps/patterns/runtime_steps.py src/apps/patterns/runtime_support.py src/apps/patterns/task_service_runtime.py src/runtime/streams/workers.py tests/apps/patterns/test_realtime_engine.py tests/apps/patterns/test_services_async.py tests/runtime/streams/test_workers.py tests/architecture/service_layer_baseline.py`

### Stage 8. Wave 2F: `anomalies`

Status: done

Goal:

- remove dict-shaped anomaly service contracts for detection and enrichment flows
- remove `schemas` transport leakage from the service layer
- move anomaly payload/enrichment shaping out of `anomaly_service.py`
- reduce the anomaly service hotspot below module/class thresholds

Planned deliverables:

- [x] anomaly domain contracts moved out of `schemas.py`
- [x] typed anomaly service results for detection batches and enrichment
- [x] pure payload/enrichment engine helpers plus extracted detection runner
- [x] task boundary serializers adapted to preserve external dict payloads
- [x] pure anomaly engine tests and persistence contract tests aligned with final contracts

Verification:

- [x] `cd backend && uv run pytest tests/apps/anomalies/test_payload_engine.py tests/apps/anomalies/test_persistence_contracts.py tests/architecture`
- [x] `cd backend && uv run ruff check src/apps/anomalies/contracts.py src/apps/anomalies/schemas.py src/apps/anomalies/engines src/apps/anomalies/results.py src/apps/anomalies/detection_runner.py src/apps/anomalies/services/anomaly_service.py src/apps/anomalies/tasks/anomaly_enrichment_tasks.py tests/apps/anomalies/test_payload_engine.py tests/apps/anomalies/test_persistence_contracts.py tests/architecture/service_layer_baseline.py`

### Stage 9. Wave 3A: `market_data`

Status: done

Goal:

- remove `dict/status` public contracts from history sync services
- remove transport DTO imports from `backend/src/apps/market_data/services.py`
- split bulky write/history helper orchestration out of `services.py`
- keep task payloads stable by shaping dict results only at the task boundary

Planned deliverables:

- [x] service-side market-data contracts outside `schemas.py`
- [x] typed history sync result contract
- [x] extracted write-side command support and history sync helpers outside `services.py`
- [x] task serializers adapted to preserve external dict payloads
- [x] service tests and architecture baseline aligned with final contracts

Verification:

- [x] `cd backend && uv run pytest tests/apps/market_data/test_services.py tests/apps/market_data/test_tasks.py tests/apps/market_data/test_persistence_contracts.py tests/architecture`
- [x] `cd backend && uv run ruff check src/apps/market_data/command_support.py src/apps/market_data/contracts.py src/apps/market_data/history_sync.py src/apps/market_data/results.py src/apps/market_data/services.py src/apps/market_data/tasks.py tests/apps/market_data/test_services.py tests/apps/market_data/test_tasks.py tests/apps/market_data/test_persistence_contracts.py tests/architecture/service_layer_baseline.py`

### Stage 10. Wave 3B: `news`

Status: done

Goal:

- remove remaining provider/router/schema leaks from the news service layer
- replace dict-shaped poll results with typed service contracts
- keep provider fetch/output shaping outside public service methods

Planned deliverables:

- [x] service-side news contracts outside `schemas.py`
- [x] typed polling result contracts and task-boundary serializers
- [x] polling, telegram onboarding and telegram provisioning moved to focused modules
- [x] telegram wizard routing moved to API helper outside the service layer
- [x] news tests and architecture baseline aligned with final contracts

Verification:

- [x] `cd backend && uv run pytest tests/apps/news/test_services.py tests/apps/news/test_views.py tests/apps/news/test_pipeline.py tests/apps/news/test_persistence_contracts.py tests/architecture`
- [x] `cd backend && uv run ruff check src/apps/news/contracts.py src/apps/news/results.py src/apps/news/polling.py src/apps/news/telegram_onboarding.py src/apps/news/telegram_provisioning.py src/apps/news/services.py src/apps/news/schemas.py src/apps/news/tasks.py src/apps/news/api/onboarding_endpoints.py src/apps/news/api/onboarding_wizard.py tests/apps/news/test_services.py tests/architecture/service_layer_baseline.py`

### Stage 11. Wave 3C: `indicators`

Status: done

Goal:

- remove cross-domain market-data model/repository access from indicator services
- split heavy indicator calculations from orchestration
- reduce indicator hotspot size below architecture thresholds

Planned deliverables:

- [x] focused result/support modules for indicator analytics, snapshot capture and scheduler flows
- [x] analytics service kept test-seam compatible while heavy helper implementation moved out of the hotspot
- [x] feature snapshot and scheduler services moved out of `services.py`
- [x] direct market-data model/repository imports removed from the service file
- [x] indicators tests and architecture baseline aligned with final shape

Verification:

- [x] `cd backend && uv run pytest tests/apps/indicators/test_analytics_helpers.py tests/apps/indicators/test_flow_radar_snapshots_services.py tests/apps/indicators/test_persistence_contracts.py tests/architecture`
- [x] `cd backend && uv run ruff check src/apps/indicators/results.py src/apps/indicators/service_support.py src/apps/indicators/feature_snapshot_service.py src/apps/indicators/analysis_scheduler_service.py src/apps/indicators/services.py src/apps/indicators/snapshots.py tests/apps/indicators/test_analytics_helpers.py tests/apps/indicators/test_flow_radar_snapshots_services.py tests/apps/indicators/test_persistence_contracts.py tests/architecture/service_layer_baseline.py`

### Stage 12. Wave 3D: `portfolio`

Status: done

Goal:

- remove payload summary helpers from portfolio public contracts
- remove direct market-data/signals model and repository imports from portfolio services
- reduce portfolio hotspots below architecture thresholds

Planned deliverables:

- [x] focused result/serializer/support modules for portfolio sync and action flows
- [x] pure rebalance calculation moved to `engines/` while `PortfolioService` kept wrapper compatibility for existing tests
- [x] payload summary helpers removed from portfolio public result contracts
- [x] direct market-data/signals model and repository imports removed from `portfolio/services.py`
- [x] portfolio tests and architecture baseline aligned with final shape

Verification:

- [x] `cd backend && uv run pytest tests/apps/portfolio tests/architecture`
- [x] `cd backend && uv run ruff check src/apps/portfolio/action_support.py src/apps/portfolio/results.py src/apps/portfolio/serializers.py src/apps/portfolio/services.py src/apps/portfolio/sync_support.py src/apps/portfolio/tasks.py src/apps/portfolio/engines tests/apps/portfolio/test_rebalance_engine.py tests/apps/portfolio/test_services_selectors_cache.py tests/architecture/service_layer_baseline.py`

### Stage 13. Governance Artifact A: service-layer scorecard

Status: done

Goal:

- generate a live service-layer scorecard from codebase facts
- publish the scorecard as a CI artifact
- keep scorecard generation covered by architecture tests

Planned deliverables:

- [x] reusable scorecard builder aligned with service-layer policy scanners
- [x] Markdown + JSON export script under `backend/scripts/`
- [x] architecture workflow updated to generate and upload the artifact
- [x] architecture tests cover scorecard generation/rendering

Verification:

- [x] `cd backend && uv run pytest tests/architecture`
- [x] `cd backend && uv run python scripts/export_service_layer_scorecard.py --markdown-output /tmp/service-layer-scorecard.md --json-output /tmp/service-layer-scorecard.json`

### Stage 14. Governance Artifact B: ADR package

Status: done

Goal:

- add short ADRs for the most contested service-layer rules
- link the ADR package back to architecture policy and the canonical reference module
- keep ADR package presence visible in CI

Planned deliverables:

- [x] ADR for caller-owned commit boundary
- [x] ADR for analytical engine IO boundary
- [x] ADR for transport shaping outside services
- [x] ADR for async-class-first orchestration vs pure analytical engines
- [x] ADR for post-commit side effects
- [x] architecture test proving ADR package exists
- [x] explicit references from service-layer policy and canonical `signals` reference module

Verification:

- [x] `cd backend && uv run pytest tests/architecture`
- [x] `cd backend && uv run ruff check tests/architecture/service_layer_policy.py tests/architecture/test_service_layer_adrs.py src/apps/signals/services/__init__.py`

### Stage 15. Governance Artifact C: runtime idempotency/retry/concurrency rules

Status: done

Goal:

- define per-domain runtime rules for background orchestration
- document idempotency, retry and concurrency semantics on real task/consumer paths
- keep the runtime matrix present in architecture governance

Planned deliverables:

- [x] service-layer runtime policy document with per-domain matrix
- [x] explicit global rules for locks, deduplication and retries
- [x] architecture test proving the runtime policy document exists

Verification:

- [x] `cd backend && uv run pytest tests/architecture`
- [x] `cd backend && uv run ruff check tests/architecture/test_service_layer_runtime_policies_doc.py`

### Stage 16. Governance Artifact D: performance budgets

Status: done

Goal:

- define explicit performance budgets for heavy sync/job paths
- tie hard budgets to real runtime locks or tracked-operation boundaries
- keep the budget document present in architecture governance

Planned deliverables:

- [x] service-layer performance budget document with target/alert/hard thresholds
- [x] budget matrix tied to real heavy job paths across domains
- [x] architecture test proving the budget document exists

Verification:

- [x] `cd backend && uv run pytest tests/architecture`
- [x] `cd backend && uv run ruff check tests/architecture/test_service_layer_performance_budgets_doc.py`

## Execution Log

- [x] Stage 1 complete: architecture governance baseline and CI gate landed.
- [x] Stage 2 complete: canonical `signals` rewrite landed with dedicated `services/`, pure `engines/`, explicit adapters and typed result contracts.
- [x] Stage 3 complete: `predictions` moved to service/engine/integration form and no longer exposes summary-shaped public result helpers.
- [x] Stage 4 complete: `cross_market` moved to service/engine/integration form and no longer mixes orchestration with correlation/sector/leader computation.
- [x] Stage 5 complete: `control_plane` now uses `services/` + `engines/`, read-side wrappers were removed in favor of query services, and post-commit control events moved behind an explicit dispatcher.
- [x] Stage 6 complete: `market_structure` now uses `services/` + `engines/`, pure health/backoff/quarantine rules, typed poll/ingest results, and no longer mixes onboarding transport shaping into service code.
- [x] Stage 7 complete: `patterns/task_service_runtime` now uses pure realtime engines plus typed runtime results, direct cross-domain imports left the service file, and runtime workers consume attribute-based contracts instead of dict payloads.
- [x] Stage 8 complete: `anomalies` now uses typed service results, no longer imports anomaly transport schemas from the service layer, and delegates anomaly payload/enrichment shaping outside `anomaly_service.py`.
- [x] Stage 9 complete: `market_data` now uses typed history sync results, task-boundary dict serialization, extracted write/history support outside `services.py`, and no longer carries market-data transport DTO imports in the service layer.
- [x] Stage 10 complete: `news` now uses typed polling results, focused polling/onboarding/provisioning modules, and no longer keeps router/schema leaks in `news/services.py`.
- [x] Stage 11 complete: `indicators` now keeps analytics test seams intact while snapshot/scheduler/results/support moved out of the hotspot, and the service file no longer imports market-data models or repositories directly.
- [x] Stage 12 complete: `portfolio` now uses typed public result contracts plus serializer helpers, pure rebalance calculation lives in `engines/`, and the service file no longer mixes cross-domain imports with balance/action orchestration hotspots.
- [x] Stage 13 complete: a live service-layer scorecard is now generated from architecture policy scanners, exported as Markdown/JSON, and uploaded by CI as an artifact.
- [x] Stage 14 complete: the service-layer ADR package now captures the core boundary decisions, is referenced from policy/reference code, and is checked by the architecture test suite.
- [x] Stage 15 complete: runtime idempotency, retry and concurrency rules are now documented per domain for real job/consumer entry points and checked for presence by the architecture suite.
- [x] Stage 16 complete: heavy service-layer job paths now have explicit target/alert/hard performance budgets tied to real runtime locks and tracked-operation boundaries.
