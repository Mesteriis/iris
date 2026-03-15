# ADR 0005: Analytical Snapshot API Semantics

## Status

**Accepted**

## Date

2025-01-19

## Context

Analytical APIs differ from CRUD APIs.

**Responses may be:**

- cached
- computed
- not perfectly fresh

Without explicit freshness semantics, clients can incorrectly assume the data is current.

## Decision

All analytical responses must include snapshot metadata.

**Examples:**

- `generated_at`
- `freshness_class`
- `staleness_ms`

HTTP responses must support:

- `Cache-Control`
- `ETag`
- `Last-Modified`
- deterministic `304 Not Modified`

## Consequences

### Positive

- honest analytical-data semantics
- safe caching support

### Negative

- more complex API contracts

## See also

- Applies to all API design in IRIS
