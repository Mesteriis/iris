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
- `scorecard automation`: pending
- `ADR package`: pending
- `service hotspot clean rewrites`: in progress

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

- [ ] Wave 2D hotspot cutover: `market_structure`

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
- [ ] Wave 2D: `market_structure`
- [ ] Wave 2E: `patterns/task_service_runtime`
- [ ] Wave 2F: `anomalies`
- [ ] Wave 3: `market_data`, `news`, `indicators`, `portfolio`

Правило для каждой rewrite-задачи:

- one domain rewrite = one final-form cutover
- no stop at temporary `dict/status` compatibility
- no stop at temporary giant-module split without final contracts
- no `AsyncSession`/transport leak carried forward “до следующего этапа”

### 4. Governance Artifacts

- [ ] generate architecture scorecard from codebase facts
- [ ] publish scorecard as CI artifact
- [ ] add ADRs for transaction boundary, engine IO boundary, transport shaping, async-class-first scope and post-commit side effects
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
