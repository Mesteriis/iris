# ADR 0011: Analytical Engines Never Fetch

## Status

Accepted

## Date

2025-02-03

## Context

The old hotspot modules mixed mathematical evaluation with database and provider access:

- analytical logic was difficult to test without runtime wiring;
- deterministic computation was hidden behind repository calls;
- engines could not be reused safely because their correctness depended on live IO.

The service-layer standard separates orchestration from computation. That separation fails if analytical engines are allowed to fetch their own inputs.

## Decision

Analytical engines may not perform IO and may not fetch their own data.

The practical rule is:

- services, repositories and integrations gather inputs;
- engines receive typed inputs and return typed outputs;
- engines stay pure with no database, HTTP, queue, cache or settings fetches;
- if a domain needs cross-domain data, the service layer introduces an explicit adapter before calling the engine.

## Consequences

This preserves deterministic analytical behavior:

- engine tests run without DB/runtime setup;
- orchestration and retry behavior stay outside the math layer;
- cross-domain boundaries remain explicit instead of leaking into engine code;
- “just fetch what the engine needs” is no longer an acceptable shortcut.


## See also

- [ADR 0009: Signals Service/Engine Split](0009-canonical-signals-service-engine-split.md) — canonical example
- [ADR 0013: Async Classes for Orchestration](0013-async-classes-orchestration-pure-functions.md) — pure function principle
