# ADR 0012: Services Return Domain Contracts, Not Transport Payloads

## Status

Accepted

## Date

2025-02-04

## Context

Before the refactor, many services returned `dict[str, object]` payloads or helper methods like `to_summary()` / `to_payload()`:

- service contracts leaked HTTP/task/cache shaping concerns;
- orchestration tests had to inspect transport-shaped payloads instead of domain results;
- transport compatibility helpers tended to survive long after the service rewrite was supposedly finished.

IRIS needs the service layer to represent application outcomes, not transport serialization.

## Decision

Public service methods return typed domain/application contracts.

The practical rule is:

- service results are dataclasses or equivalent typed contracts;
- transport shaping happens at HTTP presenters, task boundaries, cache writers or explicit serializer modules;
- public service contracts do not expose `to_summary()` or `to_payload()` helpers;
- if a transport needs a dict payload, the caller serializes the typed result outside the service layer.

## Consequences

This keeps service boundaries stable and intention-revealing:

- services stay transport-agnostic;
- task and API boundaries remain the only places that shape wire payloads;
- architectural policy can reject summary helpers mechanically;
- future rewrites cannot stop at “typed inside, dict outside the same service module.”


## See also

- [ADR 0009: Signals Service/Engine Split](0009-canonical-signals-service-engine-split.md) — canonical example
- [ADR 0006: Portfolio Engine Separation](0006-portfolio-engine-separation.md) — application outcome pattern
