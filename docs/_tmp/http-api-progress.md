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
- `idempotency/concurrency runtime enforcement`: done
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
- [x] Runtime deduplication for async job triggers and explicit concurrency conflicts for stale control-plane draft apply
- [x] PR review checklist and API governance CI workflow

## Current Block

- [ ] Consistency/freshness metadata for analytical reads
  Scope:
  - formalize `generated_at`, `consistency` and `staleness_ms` for derived read payloads
  - classify analytical endpoints by freshness semantics without polluting simple CRUD/read contracts
  - connect read presenters/page envelopes to explicit data-semantics metadata where it matters

## Remaining Blocks

- [ ] Cache/revalidation HTTP policy

## Idempotency And Concurrency Runtime Enforcement

- [x] `core/http/operation_store.py` now deduplicates active async/job dispatches on Redis-backed deduplication slots instead of blindly creating a new operation on every trigger
- [x] repeated `news`, `market_data`, `market_structure` and `hypothesis_engine` job-trigger requests now return the existing `operation_id` with `deduplicated=true` and a stable repeat message
- [x] deduplication slots are released automatically on terminal operation states, so retries after failure/completion create a new tracked operation instead of reusing stale state
- [x] `control_plane` stale draft apply now raises a typed `409 concurrency_conflict` response with structured version details instead of falling back to generic invalid-state handling

## Operation Resource Model

- [x] async/job endpoints now return typed accepted contracts with stable `operation_id`
- [x] `core/http/operation_store.py` persists operation status, result and event history in Redis
- [x] system HTTP surface exposes `GET /operations/{operation_id}`, `/result` and `/events`
- [x] job dispatchers in `news`, `market_data`, `market_structure` and `hypothesis_engine` now create tracked operations before queue dispatch
- [x] TaskIQ job entrypoints update operation lifecycle through `run_tracked_operation(...)`

## Recent Commits

- `23ace85` `feat(api): add operation resource model for async jobs`
- `7ca3177` `feat(api): export capability catalog`
- `9e526ca` `ci(api): enforce governance snapshots`
- `7ee0eab` `feat(api): check http availability matrix snapshots`
- `6b1ac24` `docs(api): add endpoint review checklist`
- `a04aa62` `feat(api): export http availability matrix`
