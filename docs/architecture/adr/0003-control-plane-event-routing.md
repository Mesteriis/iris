# ADR 0003: Control Plane for Event Routing

## Status

**Accepted**

## Date

2025-01-17

## Context

In event-driven systems, event routing is often hardcoded:

- consumer groups
- topic subscriptions
- handler mappings

That makes the following harder:

- experimentation
- staged rollout
- shadow routing
- runtime topology changes

## Decision

IRIS introduces a control plane for event routing.

**Core entities:**

- `event_definitions`
- `event_consumers`
- `event_routes`
- `topology_config_versions`
- `topology_drafts`

The runtime dispatcher reads the active topology snapshot and delivers events to the appropriate consumers.

## Consequences

### Positive

- flexible routing control
- shadow-processing support
- safer topology changes

### Negative

- additional runtime complexity
- topology version control is required

## See also

- [ADR 0001: Event-Driven Runtime](0001-event-driven-runtime.md) — event-pipeline foundation
