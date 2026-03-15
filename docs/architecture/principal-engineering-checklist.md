# Principal Engineering Checklist

## Status

Accepted as an active engineering invariant checklist for design and review work.

## Scope

This document defines the architectural invariants that must remain true as IRIS evolves.

IRIS is not a simple service. It is a multi-layer analytical platform composed of:

- event-driven analytics runtime
- domain-oriented market-intelligence modules
- persistence governance layer
- portfolio decision engine
- cross-market intelligence
- API governance surface

To keep the system stable over time, the following engineering rules must always hold.

## 1. Architectural Layering Must Never Collapse

IRIS follows a strict layered structure:

- `core`
- `apps`
- `runtime`
- `api`

Responsibilities must remain clearly separated.

`core` contains:

- configuration
- database primitives
- transaction boundaries
- shared infrastructure

`apps` contain domain logic such as:

- market analysis
- signal generation
- portfolio engine
- predictions
- strategies

`runtime` contains execution wiring:

- event streams
- orchestration
- schedulers
- workers

`api` exposes domain contracts and must never contain business logic.

Violation of this layering rule introduces architectural debt.

## 2. Database Access Must Remain Centralized

Direct database access outside the persistence layer is forbidden.

All write operations must go through repositories.

All read operations must go through query services.

Routes, workers, and services must not directly manipulate database sessions.

The Unit of Work implementation is the single authority controlling:

- commit
- rollback
- transaction boundaries

Persistence rules are architectural invariants.

## 3. Event Pipeline Must Remain the Only Runtime Entry Path

Runtime analytics must always enter the system through the event pipeline:

- polling -> candle ingestion -> event emission -> analytics workers

No alternative trigger paths should be introduced.

Direct invocation of analytics services from routes or scripts is prohibited.

The event bus guarantees:

- ordering
- decoupling
- retry safety
- crash recovery

Breaking this rule introduces race conditions and inconsistent state.

## 4. Domain Modules Must Own Their Contracts

Each domain module must define its own:

- API router
- schemas
- services
- repositories
- read models

Modules must not leak internal persistence models across boundaries.

External callers should interact with:

- API schemas
- typed read models
- domain services

This rule preserves domain isolation and prevents cross-module coupling.

## 5. Event Routing Must Remain Configurable

Event routing must be managed by the control plane.

Producers publish events to the canonical ingress stream.

The dispatcher decides delivery targets using the topology snapshot.

Routing logic must not be hardcoded inside domain modules.

This separation allows:

- runtime topology changes
- safe experimentation
- shadow routes
- staged deployments

## 6. Analytical Layers Must Remain Bounded

IRIS contains many analytical subsystems:

- pattern detection
- market-regime analysis
- cross-market intelligence
- signal fusion
- risk evaluation
- strategy discovery

Each layer must remain conceptually independent.

Layers must communicate through well-defined contracts.

Hidden cross-layer dependencies are prohibited.

If a subsystem depends on internal behavior of another subsystem, the design must be reconsidered.

## 7. Signal Fusion Must Remain Explainable

Signal fusion is responsible for combining signals from multiple analytical layers.

Fusion logic must remain interpretable.

Each decision must expose:

- contributing signals
- suppressed signals
- weighting factors
- regime adjustments
- risk adjustments

If fusion weights become opaque or too numerous, the model must be simplified.

Signal fusion is not a black-box ML system.

## 8. Portfolio Engine Must Be Deterministic

Portfolio actions must be deterministic.

The same inputs must always produce the same actions.

Portfolio rules must remain simple and auditable.

Key invariants include:

- capital allocation limits
- position sizing logic
- risk constraints
- exposure limits

Portfolio actions must always be explainable through structured reasoning.

## 9. API Surface Must Remain Governed

IRIS API is treated as a governed interface surface.

Each endpoint must define:

- operation identity
- capability metadata
- idempotency rules
- execution mode
- resource requirements

OpenAPI snapshots must remain stable across releases.

Changes to the API surface must be intentional and traceable.

## 10. Analytical Snapshots Must Declare Freshness

Analytical responses must describe their consistency properties.

Responses must include metadata such as:

- generated timestamp
- freshness classification
- staleness information

Cache semantics must be explicit.
