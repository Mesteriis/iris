# ADR 0010: Caller Owns Commit Boundary

## Status

Accepted

## Date

2025-02-02

## Context

The service-layer refactor made transaction handling one of the main sources of regressions:

- large services used to mix orchestration with hidden commit points;
- background jobs, API handlers and runtime consumers could not reason clearly about rollback behavior;
- post-commit side effects became unsafe when a service committed internally and a caller still assumed it owned the unit of work.

IRIS needs one stable rule for transaction ownership across API, worker and orchestration entry points.

## Decision

The caller owns the commit boundary.

The practical rule is:

- services may load, mutate, flush and return typed results;
- services must not call `commit()` internally;
- API handlers, jobs and consumers commit through their unit of work after service execution succeeds;
- post-commit side effects are triggered only after the caller commits successfully.

## Consequences

This keeps transactional behavior explicit and testable:

- rollback behavior can be verified at the caller boundary;
- services stay reusable across HTTP, worker and internal orchestration paths;
- side effects do not race ahead of failed transactions;
- future service rewrites should treat `flush()` as the maximum write-side responsibility inside the service layer.

## See also

- [ADR 0014: Side Effects Execute Post-Commit](0014-side-effects-post-commit-only.md) — side effect safety
- [ADR 0002: Persistence Architecture](0002-persistence-architecture.md) — infrastructure foundation
