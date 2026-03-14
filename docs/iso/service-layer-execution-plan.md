# IRIS Service Layer Execution Plan

## Source Of Truth

- audit standard: `docs/iso/service-layer-refactor-audit.md`
- progress board: `docs/iso/service-layer-progress.md`

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

Status: next

- [ ] `control_plane`

### Stage 6. Wave 2D: `market_structure`

Status: pending

- [ ] `market_structure`

### Stage 7. Wave 2E: `patterns/task_service_runtime`

Status: pending

- [ ] `patterns/task_service_runtime`

### Stage 8. Wave 2F: `anomalies`

Status: pending

- [ ] `anomalies`

### Stage 9. Wave 3 Hotspots

Status: pending

- [ ] `market_data`
- [ ] `news`
- [ ] `indicators`
- [ ] `portfolio`

## Execution Log

- [x] Stage 1 complete: architecture governance baseline and CI gate landed.
- [x] Stage 2 complete: canonical `signals` rewrite landed with dedicated `services/`, pure `engines/`, explicit adapters and typed result contracts.
- [x] Stage 3 complete: `predictions` moved to service/engine/integration form and no longer exposes summary-shaped public result helpers.
- [x] Stage 4 complete: `cross_market` moved to service/engine/integration form and no longer mixes orchestration with correlation/sector/leader computation.
- [ ] Stage 5 not started in code yet.
