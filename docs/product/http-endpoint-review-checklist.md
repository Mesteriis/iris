# HTTP Endpoint Review Checklist

Use this checklist for every PR that adds, removes, or changes HTTP endpoints in IRIS.

## Scope

This checklist applies to:

- new endpoints
- changed request or response contracts
- route exposure changes by `mode` or `profile`
- endpoint moves between `read`, `commands`, `jobs`, `webhooks`, `streams`, `onboarding`, or `admin`
- changes to error semantics, idempotency, or async operation behavior

## Required Classification

Every changed endpoint must have an explicit answer for:

- owner domain
- endpoint class: `resource`, `projection`, `operation`, `job`, `webhook`, `stream`
- contract audience: `public_read`, `operator_control`, `internal_platform`, `external_ingest`, `embedded_ha`
- launch modes: `full`, `local`, `ha_addon`
- deployment profiles: `platform_full`, `platform_local`, `ha_embedded`
- execution model: `sync` or `async`
- idempotency policy: `strict`, `conditional`, `non_idempotent`
- operation resource required: `yes` or `no`

## Transport Rules

- [ ] Handler lives in `src/apps/<domain>/api/*_endpoints.py`.
- [ ] Handler file contains only async endpoint functions and router declarations.
- [ ] Handler receives only ready services/facades or standardized access dependencies via `Depends(...)`.
- [ ] Handler does not receive `AsyncSession`, repository, raw Redis client, raw queue client, or provider SDK directly.
- [ ] Request and response contracts use `Pydantic` schemas.
- [ ] Response model is explicit for every non-`204` endpoint.
- [ ] Error mapping goes through shared/domain API error helpers, not ad-hoc `HTTPException` branching.

## URL and Surface Semantics

- [ ] Route class is correct: `resource`, `projection`, `operation`, `job`, `webhook`, or `stream`.
- [ ] Endpoint is mounted under the owning domain router only.
- [ ] URL change, if any, is explicitly called out in migration notes.
- [ ] Mode/profile exposure is intentional and reflected in router assembly.
- [ ] `ha_addon` exposure was reviewed explicitly.

## Execution Semantics

- [ ] Command endpoints use the shared command execution flow.
- [ ] Async triggers return a typed accepted/operation contract instead of ad-hoc payloads.
- [ ] Idempotency or duplicate-trigger behavior is documented.
- [ ] Conflict/concurrency behavior is defined for mutable resources.
- [ ] Long-running or streaming behavior is isolated behind transport adapters, not in the handler body.

## Data Semantics

- [ ] Pagination is standardized for collection endpoints.
- [ ] Filter and sort parameter names follow the shared naming policy.
- [ ] Large collections do not return a naked list.
- [ ] Analytical responses expose consistency/freshness metadata when relevant.
- [ ] Response DTO does not leak persistence-only fields.

## Errors and Observability

- [ ] Error code and HTTP status follow the shared taxonomy.
- [ ] Retryability is clear for failed commands/jobs/webhooks.
- [ ] Request/correlation identifiers are preserved where relevant.
- [ ] Mode-specific unavailability maps to a deliberate API error, not accidental omission inside handler logic.

## OpenAPI and Artifacts

- [ ] Tag follows the `domain:category` convention.
- [ ] `operationId` is generated under the shared policy.
- [ ] Known error responses are documented.
- [ ] OpenAPI snapshots were regenerated or verified with `make openapi-check`.
- [ ] HTTP availability matrix was regenerated with `make api-matrix-export` when exposure changed.

## PR Notes

PR description should include:

- changed domains and endpoint classes
- user-visible contract changes
- mode/profile exposure changes
- idempotency or async-operation changes
- generated artifacts that were updated
