# Service-Layer Refactor Audit

## Goal

Close the last large architectural layer after persistence and HTTP by:

- standardizing the service layer;
- standardizing the analytical and mathematical engine layer;
- eliminating service-god modules;
- fixing strict runtime rules;
- separating orchestration from transport and persistence;
- separating orchestration from pure math and analytics;
- moving active service paths to typed contracts;
- eliminating ad-hoc `dict[str, object]` results and compatibility-shaped return payloads;
- turning key architectural rules into CI-enforced policy;
- defining a canonical reference module and a live architecture scorecard;
- performing a direct cutover to the final service form rather than staged compatibility migrations.

This is not cosmetic cleanup. Since persistence and HTTP were already standardized, the service layer also had to move directly into its final model.

## Current State

Persistence, HTTP, and planned service-layer governance are already standardized.

As of 2026-03-14:

- all stages from `docs/delivery/archive/service-layer-execution-plan.md` were completed;
- planned hotspot domains were moved to the final service/engine form;
- architecture CI, generated scorecard, ADR package, runtime policy docs, and performance budgets exist in the repository;
- remaining service-layer debt is localized rather than smeared across all hotspots.

Sections `0-20` in the historical audit explain why the refactor was required. Sections `21-26` in the original working version captured the executed end state. This normalized English version keeps the architectural conclusions.

## Main Problems

### 0. No Formal Split Between Orchestration Services and Pure Analytical Engines

This was the biggest architectural risk for math-heavy domains.

Typical failure mode:

- a service loaded data;
- made orchestration decisions;
- calculated scoring or aggregation;
- saved the result;
- sometimes built summary payloads too.

That shape made math logic:

- hard to unit test without DB or runtime wiring;
- tightly coupled to repositories, UoW, and side effects;
- hard to reuse across HTTP, jobs, and runtime flows.

### 1. Service Modules Became the New Application God Layer

Symptoms:

- one module mixed commands, jobs, provisioning, side effects, and result shaping;
- one class knew too much about the bounded context;
- one service handled mutation, analytics, publication, and summaries simultaneously.

### 2. Typed Service Result Contracts Were Applied Inconsistently

Some domains already used typed dataclass results, but many still returned:

- raw dict payloads;
- `status` vocabularies;
- summary-shaped helpers such as `to_summary()`.

That forced callers to understand ad-hoc semantics and made services look transport-like instead of application-like.

### 3. Service Layer Still Knew Too Much About Low-Level Infrastructure

Signals of the problem:

- `AsyncSession` in service constructors or helper signatures;
- module-level helper functions for write paths;
- raw publish or cache side effects inside service bodies;
- payload proxies for downstream runtime messages.

### 4. Presentation Shaping Leaked Into the Service Layer

Some services returned presentation or summary forms instead of typed domain or application results.

This repeated the same leakage problem that had already been removed from HTTP.

### 5. Side Effects Were Not Always Modeled as an Explicit Concern

Side effects were sometimes deferrable through `after_commit`, but not always formalized through explicit output ports or dispatchers.

Standard needed:

- command service changes state;
- output dispatcher or port publishes events or invalidations;
- side effects are registered as post-commit work.

### 6. Cross-Domain Coupling Was Not Fully Normalized

Risks remained:

- importing foreign repositories or models;
- manually assembling cross-domain snapshots;
- relying on convenient neighboring-domain helpers instead of explicit facades or query boundaries.

### 7. Service Module / Package Layout Was Not Standardized

The repository contained every possible variant at once:

- one giant `services.py`
- partially split helper modules
- dispatcher logic in the same file

That hurt clarity and hotspot detection.

### 8. Rules Lived More in the Document Than in the Pipeline

Until enforcement existed, rules were advisory:

- engine purity was not checked in CI;
- giant module thresholds did not fail builds;
- dict-shaped service contracts were not blocked automatically;
- `AsyncSession` leakage was not caught by tests;
- cross-domain shortcuts were not governed by architecture policy.

### 9. Structural Rules Were Stronger Than Semantic and Operational Invariants

Structure alone was not enough.

The architecture needed to define:

- deterministic result behavior;
- reentrancy expectations;
- safe retry semantics;
- when sync paths must move to job paths;
- explainability and reproducibility as part of the contract.

## Main Architectural Model: Two Layers

For math-heavy use cases, the correct standard is **service + engine**, not just “service layer.”

### Layer A — Orchestration Service

Responsible for:

- loading input through repositories or query services;
- normalizing and assembling typed engine input;
- calling the pure analytical engine;
- saving results;
- registering post-commit side effects;
- returning typed application results.

### Layer B — Analytical Engine

Responsible only for:

- computations;
- deterministic evaluation;
- math-heavy policy logic;
- typed analytical output.

The engine knows nothing about:

- database access;
- UoW;
- transport;
- provider SDKs;
- cache or queue clients.

### Async-Class-First Rule

For active application paths:

- orchestration capabilities are expressed as async classes;
- service boundaries are explicit class contracts;
- public operations are async methods.

Pure analytical math may remain pure functions, but orchestration may not collapse into anonymous helper chains.

## Target Service and Engine Standard

## 1. Service Categories

### Application Command Services

Used for synchronous write-side or use-case orchestration.

### Task / Job Services

Used for background execution paths, jobs, and scheduled work.

### Provisioning / Integration Services

Used for bounded integration workflows.

### Side-Effect Dispatchers / Output Adapters

Used for post-commit publication and external effects.

### Pure Analytical Engines

Used for math, ranking, clustering, aggregation, scoring, and deterministic evaluation.

### Pure Support / Policy Modules

Used for small deterministic support logic that does not orchestrate IO.

## 2. Analytical Engine Contract

### Normal Execution Chain

1. query/repository layer loads data
2. orchestration service assembles typed engine input
3. engine computes result
4. service persists result and registers side effects
5. caller commits transaction

### Key Rule

If the engine needs another DB query, the boundary is wrong.

Fix the input model or the projection before calling the engine.

## 3. Engine Input / Output Policy

Use dedicated typed contracts for engine input and output.

Do not pass:

- ORM entities
- raw dicts
- HTTP schemas
- repositories or query services

### Numeric Policy

Numeric semantics must be explicit:

- either `float`
- or `Decimal`
- or scaled `int`

Mixed numeric semantics without explicit conversion is forbidden.

### Time Policy

Time must be normalized before engine invocation.

### Semantic Invariant Policy

At minimum:

- timestamps sorted and normalized before the engine boundary
- weights sum to `1 ± epsilon` when normalized weighting exists
- `NaN` and `inf` forbidden at boundary
- identical input + identical versions yield identical result
- tie-break behavior deterministic and documented
- threshold crossings that affect outcome have explainability reason

## 4. Service Responsibility Contract

Services may:

- accept typed commands or context;
- load mutable state through repositories;
- call policies or support functions;
- orchestrate repository operations;
- call explicit read or query facades;
- register post-commit side effects;
- return typed result contracts;
- raise typed domain or application exceptions.

Services must not:

- accept HTTP request or response objects;
- own SQL directly outside repository boundaries;
- decide OpenAPI or HTTP semantics;
- return transport payloads;
- act as giant god facades for the entire domain.

## 5. Dependency-Injection Policy

Services may inject:

- repositories
- query services
- dispatchers
- clocks or version providers
- pure engines
- typed ports or protocols

Services must not inject directly:

- raw `AsyncSession` as the primary dependency;
- raw provider SDKs without adapters;
- transport DTOs for their own sake;
- repositories or models from neighboring bounded contexts without explicit facades.

## 6. Transaction Policy

Caller-owned transaction boundaries remain mandatory.

`flush()` may be used inside a service only when generated IDs, ordering, or locking semantics truly require it.

## 7. Result Contract Policy

Public service methods should return typed result objects, typically frozen dataclasses.

Forbidden:

- raw dict results;
- generic `{"status": ...}` payloads;
- `to_summary()` as the main public contract;
- return shapes that the caller must guess.

If a transport payload is needed, presenters or boundary adapters build it separately.

## 8. Error Policy

Services must not signal failure through payload status.

Use:

- typed result for valid business outcome
- typed domain or application exception for invalid outcome

Typed `skipped` or no-op results are allowed only when they represent genuine business semantics.

## 9. Side-Effect Policy

All meaningful external effects must go through explicit output boundaries:

- event publication
- cache invalidation
- notifications
- integration messages

Service bodies must not publish side effects inline in an ad-hoc way.

## 10. Cross-Domain Policy

Services may depend on other domains only through:

- explicit facades
- query boundaries
- shared contracts
- shared abstractions in `core` when truly platform-level

No direct import of neighboring-domain internals.

## 11. Testing Policy for Analytical Engines

Analytical engines should be covered by pure tests without DB or runtime wiring.

## 12. Logging Policy

### DEBUG

Useful for internal calculation traces and development troubleshooting.

### INFO

Useful for meaningful lifecycle and orchestration milestones.

### WARNING

Used for recoverable anomalies and degraded conditions.

### ERROR

Used for real failed operations or invariant breaks.

Logs must not replace typed result, typed error, or typed explainability contracts.

## 13. Module and Package Layout

The repository should favor:

```text
src/apps/<domain>/
  services/
  engines/
  integrations/
  results.py
  contracts.py
  support.py
```

Rather than giant monolithic `services.py` hotspots.

## 14. Naming Policy

Names should express concrete responsibility.

Prefer:

- `refresh_market_structure.py`
- `leader_score_engine.py`
- `portfolio_sync_service.py`

Avoid:

- `utils.py`
- `helpers.py`
- `manager.py`
- `processor.py`
- generic `service.py` names without actual specificity

## 15. Testing Policy

The service layer needs:

- engine purity tests
- result-contract tests
- constructor dependency checks
- service module threshold checks
- transport leakage checks
- cross-domain boundary checks

## 16. Architecture CI Policy

Rules must be machine-enforced where possible.

CI should fail when:

- engines import IO boundaries
- dict-shaped public result contracts reappear
- service modules exceed agreed hotspot thresholds
- transport leakage reaches services
- cross-domain shortcuts violate policy

## 17. Semantic Invariants and Deterministic Behavior

Important services and engines must make deterministic behavior, explainability, and reproducibility part of the contract.

## 18. Operational Reliability Policy

Service and job paths must define:

- idempotency
- retry behavior
- concurrency rules
- reentrancy assumptions

## 19. Performance Budget Policy

Heavy sync and job paths need documented target, alert, and hard budgets aligned to runtime locks and operation boundaries.

## 20. Explainability and Reproducibility Contract

Analytical services must preserve enough structure to explain outcomes and reproduce them under the same inputs and versions.

## 21. Reference Implementation: `signals`

The `signals` package serves as the canonical reference module for the service/engine split.

## 22. Architecture Scorecard

The repository exports a service-layer scorecard from codebase facts.

This is used both as documentation and as CI artifact.

## 23. ADR Package

Relevant ADRs document:

- caller-owned commit boundary
- engine IO boundary
- transport shaping
- async orchestration scope
- post-commit side effects

## 24. Direct Cutover Priorities

The program executed direct final-form cutovers rather than long compatibility stages.

Key domains were cut over in waves until the active hotspot set reached the final model.

## 25. Definition of Done

The refactor is done only if:

- service and engine boundaries are explicit;
- `signals` exists as the canonical reference module;
- public service contracts are typed;
- `AsyncSession` is absent from service constructors and public helper signatures;
- transport DTOs no longer leak into services;
- side effects sit behind explicit post-commit boundaries;
- architecture policy tests fail CI when the standard is violated;
- explainability, reproducibility, and operational invariants are covered by tests.

## 26. Main Conclusion

For IRIS, the correct standard for math-heavy domains is not “one more cleaned-up service.”

The correct standard is:

- orchestration service for IO and transactional coordination
- pure analytical engine for deterministic evaluation
- explicit typed results and explicit post-commit side effects
- CI-enforced architecture policy

That is what makes the service layer predictable for API, workers, TaskIQ jobs, and control-plane orchestration.
