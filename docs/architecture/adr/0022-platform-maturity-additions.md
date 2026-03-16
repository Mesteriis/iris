# ADR 0022: Platform Maturity Additions

## Status

**Accepted**

## Date

2026-03-01

## Context

IRIS already looks like a strong engineering product, but to move from “well-assembled system” to “mature platform,” it still needs several systemic layers.

This is not about adding random features. It is about introducing governed platform mechanisms that make the system predictable, explainable, observable, and extensible.

The eight directions below are required additions that must strengthen the existing architecture without breaking the current core.

## Decision

The decision is accepted as a platform target. Component-level status markers below track rollout maturity of each accepted direction, not the acceptance state of the ADR itself.

### 1. Capability / Feature Registry ⏳

**Status:** Not started

**Description**

A unified registry of product capabilities, configured providers, integrations, launch modes, and available features.

**Why**

So frontend, backend, CLI, integrations, and Home Assistant do not determine feature availability through scattered conditions and hidden checks.

**Rules**

- each capability must be represented as an explicit contract
- there must be one source of truth
- capability definitions must be typed
- feature availability must be determined through the registry, not arbitrary `if` statements
- the registry must account for `full`, `local`, and `addon` modes
- the registry must be available through a stable API and usable by UI surfaces

### 2. Health / Readiness / Diagnostics ⚠️

**Status:** Partially implemented — basic `/system/health` and source-health endpoints exist, but health, readiness, and diagnostics are not fully separated

**Description**

A layer for checking the state of the system and its dependencies.

**Why**

So the system can distinguish “the process is alive” from “the system is ready to serve real scenarios.”

**Rules**

- separate health, readiness, and diagnostics
- check DB, cache, broker, background workers, external providers, HA integrations, and key internal pipelines independently
- public responses must be safe and minimal
- extended diagnostics must be available only in operator-facing surfaces
- dependency statuses must be normalized
- dependency failures must use a unified error catalog

### 3. Job Control Plane ⚠️

**Status:** Partially implemented — TaskIQ is used for background jobs, but a unified control plane with standardized lifecycle, retry, cancel, and progress is not implemented

**Description**

A unified control layer for background jobs, ingestion pipelines, recalculation flows, and asynchronous operations.

**Why**

So background processes stop being hidden logic and become observable, manageable, and documented.

**Rules**

- each job must have an identifier, type, status, correlation ID, and related context
- job lifecycle must be standardized
- retry, cancel, progress, timestamps, and normalized error payloads must be supported
- the job-control API must be separated from execution code
- business logic must not depend on a concrete transport or job-runner mechanism
- all background operations must be traceable and auditable

### 4. Audit Trail / Event Timeline ✅

**Status:** Implemented — `EventRouteAuditLog` in the `control_plane` app provides a full audit trail

**Description**

A normalized log of meaningful domain events and entity state changes.

**Why**

So the system can reconstruct sequences of actions, explain why state changed, and make runtime behavior understandable.

**Rules**

- record not only failures but also meaningful domain events
- audit trail must not be replaced by technical logs
- each event must include actor, source, entity reference, timestamp, and event type
- event phrasing must be stable and UI-safe
- the timeline must be built from normalized events, not arbitrary text messages
- events must be usable both for internal analysis and for user-facing explanation

### 5. Unified Error Catalog ✅

**Status:** Implemented — `PLATFORM_ERROR_REGISTRY` in `iris/core/errors/catalog.py` provides error codes, message keys, severity, retryability, and HTTP mapping

**Description**

A unified product error catalog with codes, mappings, and rendering rules.

**Why**

To eliminate chaotic string-based errors, simplify i18n, stabilize API behavior, and provide one contract across backend, frontend, and integrations.

**Rules**

- each error must have a machine-readable code
- text must resolve through an i18n key
- user-safe messages and operator-facing details must be stored separately
- the error catalog must define severity, retryability, and HTTP mapping
- new errors outside the catalog are forbidden
- the same failure cause must produce the same code in the same context
- the error catalog must also be used in jobs, integrations, and HA flows

### 6. Policy / Rules Layer Lite ⚠️

**Status:** Partially implemented — `AnomalyPolicyEngine` exists in the anomalies app, but a general policy layer is not implemented

**Description**

A lightweight layer for rules, conditions, limits, and automatic system reactions.

**Why**

So signals, recommendations, actions, and automations are defined declaratively instead of through scattered hardcoded conditions.

**Rules**

- a rule must be a declarative object, not a hidden code condition
- a rule must include condition set, scope, cooldown, and action binding
- `dry-run` and explain mode must be supported
- side effects must not be hidden inside condition evaluation
- rules must be testable in isolation
- rules must be suitable for Home Assistant integration and internal automation flows
- the policy layer must remain extensible without becoming a heavyweight BPM engine

### 7. Explanation Layer ✅

**Status:** Implemented — the explanations app fully supports signal and decision explanation generation and storage

**Description**

A layer for explaining decisions, calculations, signals, and recommendations produced by the system.

**Why**

So analytics and automation are not perceived as a black box and can be explained to the user or operator.

**Rules**

- every meaningful decision must have an explanation contract
- explanations must reference inputs, calculation time, influence factors, and context
- explanations must not be raw debug dumps
- wording must be suitable for UI, API, and documentation
- different levels of detail must be supported for user-facing and operator-facing views
- explanations must align with the policy layer, audit trail, and error catalog

### 8. Config Governance ⚠️

**Status:** Partially implemented — `pydantic-settings` with schema-driven config exists, but effective-config display and the full precedence model are not implemented

**Description**

A governed, validated, observable configuration system.

**Why**

So system behavior across `full`, `local`, and `addon` modes is predictable, reproducible, and safe.

**Rules**

- configuration must be schema-driven
- the source of each value must be understandable
- secrets must be separated from normal configuration
- a precedence model for env, file, defaults, and runtime overrides must be fixed
- the system must be able to show effective config without leaking sensitive data
- configuration errors must be detected as early as possible
- configuration must support operator diagnostics and CI checks

## Consequences

### Positive

- IRIS becomes a platform, not just a feature set
- system behavior becomes more predictable
- multiple launch modes become easier to support
- frontend and integrations receive stable contracts
- jobs, integrations, and HA scenarios become easier to operate
- operational observability, debugging, and explainability improve
- architectural debt from string-based errors, hidden flags, and scattered configuration is reduced

### Negative

- the volume of contracts and architecture artifacts will increase
- some existing mechanisms will need normalization and unification
- additional tests, documentation, and migration passes across layers will be required
- implementation will require discipline, or duplicate half-solutions will appear

## Not in Scope

This decision does not currently include:

- full enterprise RBAC
- multi-tenant architecture
- an extension marketplace
- a heavy visual automation builder
- event sourcing as the base architectural model
- excessive microservice decomposition

## Summary

The priority should not be to grow random feature surface, but to build a platform frame around the capabilities that already exist.

These eight directions define the minimum maturity set after which IRIS can be positioned confidently as:

- an observable platform
- an explainable platform
- a governed platform
- an extensible platform
- a system suitable for integrations and multiple launch modes

## See also

- [ADR 0002: Persistence Architecture](0002-persistence-architecture.md) — infrastructure layer
- [ADR 0003: Control Plane for Event Routing](0003-control-plane-event-routing.md) — control plane
- [ADR 0016: Error Taxonomy and Boundary Localization](0016-error-taxonomy-boundary-localization.md) — unified error catalog
- [ADR 0017: Text Ownership Model and Localization Scope](0017-text-ownership-localization-scope.md) — i18n foundation

---

## Implementation Status (2026-03-15)

| # | Component | Status | Notes |
|---|-----------|--------|-------|
| 1 | Capability / Feature Registry | ⏳ Not started | |
| 2 | Health / Readiness / Diagnostics | ⚠️ Partial | `/system/health`, source health endpoints exist |
| 3 | Job Control Plane | ⚠️ Partial | TaskIQ is used, unified control plane not implemented |
| 4 | Audit Trail / Event Timeline | ✅ Done | `EventRouteAuditLog` in `control_plane` |
| 5 | Unified Error Catalog | ✅ Done | `PLATFORM_ERROR_REGISTRY` in `iris/core/errors/` |
| 6 | Policy / Rules Layer Lite | ⚠️ Partial | `AnomalyPolicyEngine` exists |
| 7 | Explanation Layer | ✅ Done | full explanations app |
| 8 | Config Governance | ⚠️ Partial | `pydantic-settings`, no effective config display |
