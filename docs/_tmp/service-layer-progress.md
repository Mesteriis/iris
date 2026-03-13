# IRIS Service Layer Refactor Progress

## Overall Status

- `service governance design`: done
- `service hotspot audit`: done
- `service package split`: pending
- `typed result contract migration`: pending
- `direct session helper cleanup`: pending
- `side-effect port standardization`: pending
- `cross-domain service boundary cleanup`: pending
- `service test contract standardization`: pending

## Completed Blocks

- [x] Defined a unified service-layer governance standard
- [x] Classified service responsibilities into command, job, provisioning, side-effect and support layers
- [x] Captured current hotspot modules and migration priorities
- [x] Defined transaction, dependency, result, error and logging policy for active services

## Current Block

- [x] Service-layer governance baseline created

## Priority Hotspots

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
- [x] services may `flush()` but do not own transaction finalization
- [x] services may register post-commit side effects only through explicit boundaries
- [x] service public methods should return typed dataclass contracts, not transport dictionaries
- [x] service public methods should raise typed application/domain exceptions for failures
- [x] cross-domain access must go through explicit service/query/facade boundaries

## Next Block

- [ ] Typed service result contracts for active dict-returning services
  Scope:
  - remove `dict[str, object]` public result contracts from `market_data`, `news`, `cross_market` and `patterns/task_service_*`
  - replace `status/reason` payloads with typed dataclass result objects
  - keep HTTP/worker payload shaping outside service public methods
