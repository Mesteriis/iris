# IRIS Service Layer Execution Plan

## Source Of Truth

- audit standard: `docs/iso/service-layer-refactor-audit.md`
- progress board: `docs/iso/service-layer-progress.md`

## Execution Rules

- one stage = one focused commit
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

Status: next

Goal:

- split `backend/src/apps/signals/services.py` into `services/`
- introduce `backend/src/apps/signals/engines/`
- remove summary-shaped contracts from public service results
- keep persistence and transport boundaries stable

Planned deliverables:

- [ ] service package split
- [ ] engine contracts and explainability contracts
- [ ] engine unit tests without DB/runtime wiring
- [ ] service tests focused on wiring and post-commit behavior
- [ ] short ADR for the canonical module

### Stage 3. Wave 2 Hotspots

Status: pending

- [ ] `market_structure`
- [ ] `control_plane`
- [ ] `cross_market`
- [ ] `predictions`
- [ ] `patterns/task_service_runtime`
- [ ] `anomalies`

### Stage 4. Wave 3 Hotspots

Status: pending

- [ ] `market_data`
- [ ] `news`
- [ ] `indicators`
- [ ] `portfolio`

## Execution Log

- [x] Stage 1 complete: architecture governance baseline and CI gate landed.
- [ ] Stage 2 not started in code yet.
