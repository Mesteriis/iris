# IRIS HTTP/API Refactor Progress

## Overall Status

- `HTTP cutover`: done
- `transport foundation`: done
- `OpenAPI governance`: done
- `mode-aware router assembly`: done
- `artifact drift control`: done
- `review governance`: done
- `capability metadata enrichment`: done
- `operation resource model`: pending
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
- [x] PR review checklist and API governance CI workflow

## Current Block

- [ ] Unified operation resource model
  Scope:
  - introduce first-class operation resource contract for async/job/apply/run flows
  - expose consistent `operation_id` read model and follow-up endpoints
  - connect capability metadata `operation_resource_required=yes` to real runtime/API behavior

## Remaining Blocks

- [ ] Hard idempotency and concurrency policy at runtime level
- [ ] Consistency/freshness metadata for analytical reads
- [ ] Cache/revalidation HTTP policy

## Recent Commits

- `7ca3177` `feat(api): export capability catalog`
- `9e526ca` `ci(api): enforce governance snapshots`
- `7ee0eab` `feat(api): check http availability matrix snapshots`
- `6b1ac24` `docs(api): add endpoint review checklist`
- `a04aa62` `feat(api): export http availability matrix`
- `fd70d8a` `feat(api): add openapi snapshot workflow`
