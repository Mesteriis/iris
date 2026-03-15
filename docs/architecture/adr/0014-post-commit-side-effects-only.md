# ADR 0014: Side Effects Execute Only Post-Commit

## Status

Accepted

## Date

2025-02-06

## Context

IRIS services often lead to events, cache refreshes or downstream notifications. Historically these side effects were sometimes emitted inline with write operations:

- events could be published for transactions that later rolled back;
- cache writes could expose state that never committed;
- retries became ambiguous because the side effect boundary was hidden inside the write path.

The refactor introduced explicit side-effect dispatchers, but the rule itself needs to be documented.

## Decision

Write-side side effects execute only after a successful caller-owned commit.

The practical rule is:

- services accumulate typed pending side effects in their result contracts;
- callers commit the unit of work first;
- dispatchers/presenters publish events, refresh caches or trigger downstream work only after commit succeeds;
- inline side effects inside write services are treated as architecture debt unless they are provably not state-coupled.

## Consequences

This makes write behavior safer and more repeatable:

- emitted events always correspond to committed state;
- retries can be designed around explicit post-commit boundaries;
- cache snapshots stop racing ahead of rolled-back writes;
- service tests and caller tests can verify side effects independently.


## See also

- [ADR 0010: Caller Owns Commit Boundary](0010-caller-owns-commit-boundary.md) — transaction ownership
- [ADR 0002: Persistence Architecture](0002-persistence-architecture.md) — persistence foundation
