# IRIS HTTP/API Refactor Progress

## Overall Status

- `HTTP cutover`: done
- `transport foundation`: done
- `OpenAPI governance`: done
- `mode-aware router assembly`: done
- `artifact drift control`: done
- `review governance`: done
- `capability metadata enrichment`: done
- `operation resource model`: done
- `idempotency/concurrency runtime enforcement`: pending
- `consistency/freshness semantics`: pending
- `cache/revalidation governance`: pending

## Completed Blocks

- [x] Root `/api/v1` tree with domain-local `build_router(mode, profile)`
- [x] Shared `core/http` package
- [x] Split `api/` packages for all active HTTP domains
- [x] Removal of legacy `views.py` entrypoints
- [x] Centralized `operationId` and OpenAPI tag policy
- [x] Committed OpenAPI snapshots with repo-root export/check workflow
- [x] Generated HTTP availability matrix with drift checks
- [x] Generated HTTP capability catalog with drift checks
- [x] Capability metadata policy over the generated catalog
- [x] Unified operation resource model for async/job endpoints
- [x] PR review checklist and API governance CI workflow

## Current Block

- [ ] Hard idempotency and concurrency policy at runtime level
  Scope:
  - formalize deduplication/repeat semantics beyond `operation_id` visibility
  - make conflict/version semantics explicit for mutable HTTP resources
  - connect capability metadata to real runtime guards for retries and concurrent mutation

## Remaining Blocks

- [ ] Consistency/freshness metadata for analytical reads
- [ ] Cache/revalidation HTTP policy

## Operation Resource Model

- [x] async/job endpoints now return typed accepted contracts with stable `operation_id`
- [x] `core/http/operation_store.py` persists operation status, result and event history in Redis
- [x] system HTTP surface exposes `GET /operations/{operation_id}`, `/result` and `/events`
- [x] job dispatchers in `news`, `market_data`, `market_structure` and `hypothesis_engine` now create tracked operations before queue dispatch
- [x] TaskIQ job entrypoints update operation lifecycle through `run_tracked_operation(...)`

## Recent Commits

- `7ca3177` `feat(api): export capability catalog`
- `9e526ca` `ci(api): enforce governance snapshots`
- `7ee0eab` `feat(api): check http availability matrix snapshots`
- `6b1ac24` `docs(api): add endpoint review checklist`
- `a04aa62` `feat(api): export http availability matrix`
- `fd70d8a` `feat(api): add openapi snapshot workflow`
