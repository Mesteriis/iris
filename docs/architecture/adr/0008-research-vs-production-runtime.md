# ADR 0008: Research vs Production Runtime

## Status

**Accepted**

## Date

2025-01-22

## Context

Analytical systems constantly generate new ideas:

- new patterns
- new signals
- new strategies

If every idea is immediately added to the runtime pipeline, the system becomes too complex too quickly.

## Decision

IRIS separates:

- the research layer
- the production runtime

New analytical methods are tested offline first.

Only after proving value are they added to the production pipeline.

## Consequences

### Positive

- runtime stability
- safer experimentation

### Negative

- a longer path for introducing new ideas

## See also

- [ADR 0001: Event-Driven Runtime Architecture](0001-event-driven-runtime.md)
- [ADR 0005: Analytical Snapshot API Semantics](0005-analytical-snapshot-api-semantics.md)
