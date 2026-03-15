# HTTP Endpoint Refactor Audit

## Goal

Bring the project’s HTTP surface to one hard standard, in the same way the repository already standardized the persistence layer.

This is not a cosmetic pass over `views.py`. It is a direct cutover that must:

- remove transport logic that expanded inside endpoint modules;
- split reads, writes, jobs, webhooks, and streaming into separate HTTP adapters;
- unify route prefixes, error mapping, response contracts, and operation endpoints;
- introduce one versioned API root: `/api/v1`;
- adopt an `async-func-first` endpoint style;
- avoid preserving old endpoint-helper patterns when they block the target structure;
- eliminate giant `views.py` files acting as a second application layer.

## Cutover Progress

The repository has already moved major parts of the surface to the new HTTP standard.

Delivered:

- root router tree moved to `backend/src/api/router.py` -> `backend/src/api/v1/router.py`;
- domain-local router assembly via `build_router(mode, profile)`;
- one versioned API root under `/api/v1`;
- root bootstrap now mounts only the API root router;
- schema generation and bootstrap tests now enforce `operationId` uniqueness, tag discipline, and mode-specific exposure;
- active runtime HTTP surface no longer depends on legacy `views.py` modules as the main integration point.

Removed:

- scattered top-level route assembly in bootstrap;
- multiple competing endpoint-entry styles;
- implicit versionless public router exposure as the default shape.

## Current HTTP Surface

Current state:

- `backend/src/core/bootstrap/app.py` mounts only the root API router;
- `backend/src/api/v1/router.py` centralizes the versioned `/api/v1` surface;
- active domains are mounted through domain-local router builders;
- the surface is mode-aware and OpenAPI-governed.

The first structural gap is already closed:

- there is an explicit `/api` root router;
- `/v1` lives below it;
- domains are mounted only below `/api/v1`.

## Main Problems

### 1. No Unified Router-Structure Standard

The endpoint layer was historically assembled inconsistently:

- sometimes `APIRouter(prefix=...)` was used cleanly, sometimes prefix ownership was smeared across decorators;
- some modules contained only read endpoints, while others mixed reads, writes, jobs, onboarding, webhooks, and auth behavior;
- naming and route ownership were inconsistent.

Consequence:

- mass refactor of URL surface becomes harder;
- shared transport rules are harder to enforce;
- modules are harder to review as bounded HTTP adapters.

### 2. `views.py` Turned Into Transport God Modules

In several domains, `views.py` accumulated:

- many endpoint categories in one file;
- manual serialization and mapping;
- manual exception translation;
- orchestration that no longer belonged in the transport layer.

### 3. Transport Mapping Leaked Into the View Layer

Representative cases included:

- response DTO shaping inline in endpoint modules;
- operational payload assembly directly in HTTP files;
- transport composition mixed with cross-domain read orchestration.

That means:

- the adapter knows too much about internal data shape;
- serialization policy is not centralized;
- endpoint files become a mixture of transport, presentation, and orchestration.

### 4. Repeated Command-Endpoint Boilerplate

Many endpoints repeated the same sequence:

1. verify existence through a query service;
2. call an application service;
3. catch a domain exception;
4. translate it into `HTTPException`;
5. call `await uow.commit()`;
6. return a response DTO.

This should be standardized rather than duplicated in dozens of handlers.

### 5. Job / Admin / Onboarding / Webhook Endpoints Mixed With Public Read Surface

The same files often mixed:

- public read endpoints;
- operator or admin commands;
- background trigger endpoints;
- onboarding flows;
- webhook and ingest endpoints.

That destroys a clean boundary between public projections and operational control surfaces.

### 6. Inconsistent Response Contracts

Response shape used to vary between:

- typed read models;
- raw `dict[str, object]` queue responses;
- fallback serialization “return whatever validates” behavior;
- ad-hoc `202` payloads;
- bare `list[...]` responses without pagination envelope.

### 7. Error-Handling Policy Was Not Centralized

Many modules translated domain exceptions into `HTTPException` inline.

The repository needed one stable model:

- shared base error framework;
- domain-local mapping extensions where necessary;
- no repeated `try/except -> HTTPException` boilerplate in handlers.

### 8. Some Endpoint Modules Held Runtime Mechanics Too

In a few places, endpoint files also performed:

- ingest-token extraction;
- native webhook orchestration;
- queue and runtime mechanics.

That logic belongs in dedicated transport helpers or service/adaptor modules, not in endpoint handlers.

### 9. URL Ownership and Resource Semantics Were Hard to Read

Many paths were hanging off `/coins/{symbol}/...` across multiple domains.

That is acceptable only if the system makes clear:

- what the canonical coin resource is;
- what are projections;
- what are analytical subresources;
- what are operational commands.

Without a standard, URL semantics become unclear.

## Target HTTP Standard

### 0. Shared Routing Hierarchy

Target routing tree:

```text
/api
  /v1
    /<domain>
```

Rules:

- `create_app()` mounts only the root API router;
- `src/api/router.py` mounts only version routers;
- `src/api/v1/router.py` mounts only domain routers;
- domain endpoint modules must not know about `/api` or `/v1`;
- the current standard introduces only `/api/v1`, not speculative future versions.

### 1. Mandatory Shared HTTP Core

Per-domain `api/` packages are not enough. The repository needs a shared transport foundation in `core/http`.

Shared core responsibilities:

- `contracts.py` — common transport DTOs and base Pydantic schemas;
- `errors.py` — shared `ApiError` contract and error-body factory;
- `responses.py` — typed helpers for `201`, `202`, `204`, list, page, and stream responses;
- `presenters.py` — presenter protocols and mapping helpers;
- `command_executor.py` — one command-execution flow with commit and error mapping;
- `launch_modes.py` — mode and profile-aware router rules;
- `tracing.py` — request, correlation, and causation propagation.

### 2. One `api/` Package per Domain and One Public Router Entrypoint

Each domain should expose exactly one public HTTP entrypoint:

```text
src/apps/<domain>/api/router.py
```

Inside the package, it may aggregate:

- `read_endpoints.py`
- `command_endpoints.py`
- `job_endpoints.py`
- `webhook_endpoints.py`
- `stream_endpoints.py`

But `bootstrap/app.py` must know only the domain root router.

### 3. Endpoint Files Must Be Async-Func-First and Contain Only Handlers

An endpoint module should contain real async handlers, not half-framework logic.

Allowed:

- route declaration
- typed request parsing
- dependency injection of already assembled application-facing interfaces
- typed response return
- domain/app error translation to HTTP

Forbidden:

- repository ownership
- business orchestration
- giant payload assembly
- raw queue dispatch
- hidden transport validation through unrelated helpers

### 4. Transport Contracts Only Through Pydantic Schemas

Rules:

- request bodies are defined through `BaseModel`;
- response contracts are defined through `BaseModel`;
- `response_model` is required for public endpoints except explicit `204` cases;
- handlers do not return ORM models, arbitrary dicts, or mixed payloads as public contracts;
- presenters map read models or result objects into Pydantic schemas.

### 5. Dependency-Injection Policy for Endpoint Layer

Endpoints should receive only application-facing dependencies:

- read facade or query service for read endpoints;
- command service for command endpoints;
- job/operation service for job endpoints;
- ingest service for webhook endpoints;
- stream adapter/service for stream endpoints;
- access or auth dependencies when needed.

Wrong patterns:

- passing `AsyncSession` into handlers;
- passing raw repositories directly;
- assembling services manually inside handlers;
- injecting raw Redis or queue clients;
- using one giant service for unrelated scenarios.

### 6. Router-Assembly Contract and Mode-Aware Mounting

Router assembly must be deterministic.

Rules:

- bootstrap mounts only the root API router;
- version router mounts only domain routers;
- domains aggregate their own subrouters;
- mode gating does not spread into individual handlers;
- preferred contract: `build_router(mode: LaunchMode, profile: DeploymentProfile) -> APIRouter`.

### 7. HTTP Adapter Responsibility Contract

HTTP adapters may only:

- parse request data;
- call query or application services;
- complete command transaction boundaries through shared helpers;
- map results through presenters;
- perform HTTP-level error mapping;
- return typed response contracts.

They must not:

- touch repositories directly;
- expose raw queue-dispatch mechanics;
- perform complex cross-domain composition without an explicit facade;
- assemble large operational payloads inline;
- parse transport headers ad hoc as business logic.

### 8. Separate Surfaces by Responsibility

At minimum:

- read surface
- command surface
- job or operation surface
- webhook or ingest surface
- stream surface

Additional separation is allowed when domain complexity requires it.

### 9. Command Endpoint Standard

Command endpoints should follow one shared flow:

1. parse typed input;
2. call application service;
3. use a shared command executor for commit;
4. map the result to a typed response;
5. translate typed domain/app exceptions through the shared error framework.

Mixed styles are not acceptable.

### 10. Unified Response Contract Standard

- `201 Created` only for creation of a canonical resource with a typed representation;
- `202 Accepted` only for queued/job/async trigger endpoints, through a typed `AcceptedResponse`;
- `204 No Content` only for delete, discard, or toggle-like operations with no response body;
- `200 OK` for synchronous mutation results when a resource representation or explicit operation payload is required.

Collection responses must not default to bare `list[...]` when the result can grow materially.

### 11. Pagination / Filter / Sort Governance

Large collections need:

- an envelope with `items`;
- page or cursor metadata;
- applied filters;
- optional sort metadata.

Field naming must be consistent across domains:

- `symbol`, `timeframe`, `source_id`, `status`, `created_after`, `created_before`
- `sort_by`, `sort_order`

The same semantics must not be expressed as `from_ts`, `start`, and `since` in different places.

### 12. Resource / Projection / Operation / Job / Webhook / Stream Policy

Each endpoint must be classified as one of:

- resource
- projection
- operation
- job trigger
- webhook/ingest
- stream

Operation endpoints must not masquerade as CRUD.

### 13. Stream Endpoint Standard

Streaming is its own transport category.

A stream endpoint should:

- authenticate and gate access;
- call a stream adapter;
- return streaming output only.

It must not contain business orchestration or unrelated state shaping.

### 14. Error Mapping Standard

Use:

- shared base translator in `core/http/errors.py`
- domain-local extensions such as `src/apps/<domain>/api/errors.py`

Policies for `400`, `401`, `403`, `404`, `409`, `422`, and `202/409` for already-running operations must be consistent.

### 15. OpenAPI Governance

OpenAPI is part of the definition of done.

The system must standardize:

- predictable response model names
- domain and surface-specific tags
- stable `operationId` naming

### 16. Launch Modes as an Architectural Constraint on HTTP Surface

Supported modes:

- `full`
- `local`
- `ha_addon`

Mode affects:

- available routers
- operational endpoints
- onboarding
- webhooks
- streams
- auth and access policy

Handlers must not decide mode availability ad hoc.

### 17. Mode-Aware Availability Matrix

Each domain needs an explicit matrix so the repository can:

- control exposure surface;
- test bootstrap deterministically;
- avoid hidden runtime branches;
- understand what is allowed in each mode.

### 18. Capability Model and Contract Audiences

Principal-grade APIs need capability-level artifacts, not only routes.

Each capability should define at least:

- audience
- exposure mode
- transport category
- idempotency model
- resource requirements

Typical audiences:

- public
- operator
- automation
- integration

### 19. Idempotency Policy

Every command and job trigger must have:

- a deduplication strategy;
- standardized already-running behavior;
- explicit `202`, `409`, or idempotent no-op semantics.

### 20. Operation Resource Model

Significant async work must be a first-class resource.

Standard flow:

1. client calls command or job endpoint;
2. API returns `202 Accepted`;
3. response includes `operation_id`;
4. operation status is observable as a resource or stream update.

### 21. Concurrency and Mutation Semantics

Mutating endpoints must define:

- whether they are idempotent;
- whether they conflict with already-running operations;
- what happens under retry;
- whether they queue or reject when an active operation exists.

### 22. Error Taxonomy

HTTP surface must align to a stable platform error taxonomy.

The same underlying failure cause should not produce unrelated transport behavior in different domains.

### 23. Consistency / Freshness Semantics

Analytical surfaces must expose:

- generation time
- freshness semantics
- cache behavior
- any staleness policy

### 24. Tracing Contract

HTTP transport must carry:

- request ID
- correlation ID
- causation ID

These must be governed centrally rather than improvised per endpoint.

### 25. Deployment Profiles and HA-Specific Policy

HA-specific exposure must remain explicit and governed.

The HA embedded profile must not accidentally inherit the full operator/admin surface.

### 26. Lifecycle, SLO, Caching, and Review Governance

Endpoints should also be reviewed against:

- lifecycle expectations
- performance and caching behavior
- review and release governance

### 27. Governance Scope by Endpoint Class

Rules should be enforced differently where needed, but the classes themselves must be explicit and consistent.

### 28. No Fallback Serialization

No endpoint should rely on “serialize whatever this object looks like.”

If a public transport contract exists, it must be typed and explicit.

## What To Do by Module

The refactor program already completed the main domain cutovers:

- `market_structure` [done]
- `control_plane` [done]
- `signals` [done]
- `news` [done]
- `market_data` [done]
- `hypothesis_engine` [done]
- `patterns` [done]
- `indicators` [done]
- `portfolio` [done]
- `predictions` [done]
- `system` [done]

## Recommended Work Order

1. fix root routing and versioned API assembly
2. standardize shared HTTP core
3. split endpoint surfaces by responsibility
4. standardize command execution and response contracts
5. stabilize OpenAPI governance and mode-aware exposure
6. finish domain-by-domain cutovers with no fallback compatibility layers

## Migration Rules

- no giant compatibility shims that become the new norm;
- no preserving legacy `views.py` as the main domain entrypoint;
- no raw transport leakage carried forward “until later”;
- each domain cutover should land in final form, not in half-clean intermediate state.

## Definition of Done

The HTTP refactor is done only if:

- bootstrap mounts only the root API router;
- domain HTTP entrypoints are explicit and singular;
- `views.py` no longer acts as the public god-module pattern;
- command execution is standardized;
- response contracts are typed and explicit;
- error mapping is centralized and domain-extendable;
- mode-aware availability is governed;
- OpenAPI naming and tags are stable;
- async work is exposed through first-class operation resources;
- CI and docs enforce the resulting standard.
