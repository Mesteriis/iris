# IRIS Service And Analytical Engine Refactor Progress

## Overall Status

- `service governance design`: done
- `service hotspot audit`: done
- `analytical engine governance design`: done
- `async-class-first rule`: done
- `service/engine split standard`: done
- `service package split`: pending
- `analytical engine extraction`: pending
- `typed result contract migration`: pending
- `typed analytical input/output contracts`: pending
- `direct session helper cleanup`: pending
- `side-effect port standardization`: pending
- `cross-domain service boundary cleanup`: pending
- `service test contract standardization`: pending

## Completed Blocks

- [x] Defined a unified service-layer governance standard
- [x] Defined a separate pure analytical engine standard for math-heavy domains
- [x] Locked `async-class-first` as the default rule for active orchestration boundaries
- [x] Classified service responsibilities into command, job, provisioning, side-effect and support layers
- [x] Classified the engine layer as pure compute with no hidden fetch/persist side effects
- [x] Captured current hotspot modules and migration priorities
- [x] Defined transaction, dependency, result, error and logging policy for active services

## Current Block

- [x] Service-and-engine governance baseline created

## Priority Hotspots

- [ ] `signals`, `indicators`, `cross_market`, `predictions`, `patterns/runtime` and `anomalies` extract explicit analytical engines from orchestration services
- [ ] `market_structure/services.py` split into bounded service modules
- [ ] `control_plane/services.py` split into bounded service modules
- [ ] `signals/services.py` split into bounded service modules
- [ ] `market_data/services.py` migrate from ad-hoc dict/status returns to typed result contracts
- [ ] `news/services.py` migrate from ad-hoc dict/status returns to typed result contracts
- [ ] `cross_market/services.py` remove summary-shaped public contracts from active service methods
- [ ] `patterns/task_service_*` migrate job/service results to typed contracts
- [ ] `market_data/services.py` and `control_plane/services.py` remove direct session-shaped helper contracts from active service path

## Current Standard

- [x] caller owns `commit()`
- [x] active orchestration boundaries are `async-class-first`
- [x] services may `flush()` but do not own transaction finalization
- [x] services may register post-commit side effects only through explicit boundaries
- [x] orchestration service loads/prepares/persists, analytical engine computes only
- [x] analytical engines do not fetch, persist or dispatch
- [x] service public methods should return typed dataclass contracts, not transport dictionaries
- [x] engine public functions/classes should accept typed input contracts and return typed result contracts
- [x] service public methods should raise typed application/domain exceptions for failures
- [x] cross-domain access must go through explicit service/query/facade boundaries

## Next Block

- [ ] Analytical engine extraction and typed result contracts for active math-heavy services
  Scope:
  - extract pure compute layer from `signals`, `indicators`, `cross_market`, `predictions`, `patterns/runtime` and `anomalies`
  - remove `dict[str, object]` public result contracts from `market_data`, `news`, `cross_market` and `patterns/task_service_*`
  - introduce explicit analytical input/output dataclasses for extracted engines
  - replace `status/reason` payloads with typed dataclass result objects
  - keep HTTP/worker payload shaping outside service public methods
  - keep all data fetching and persistence outside analytical engines
