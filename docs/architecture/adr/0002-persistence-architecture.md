# ADR 0002: Persistence Architecture

## Status

**Accepted**

## Date

2025-01-16

## Context

In the early project shape, database access happened directly from multiple parts of the codebase:

- API routes
- workers
- services

That led to:

- smeared transaction boundaries
- N+1 queries
- hard-to-test code

## Decision

IRIS adopts a standardized persistence architecture.

**Rules:**

- write-side logic goes through **repositories**
- read-side logic goes through **query services**
- transaction boundaries are controlled by **Unit of Work**
- read paths use immutable typed models
- routes and workers do not work directly with `AsyncSession`

## Consequences

### Positive

- predictable transactions
- simpler testing
- N+1 prevention

### Negative

- more infrastructure code
- stronger development discipline required

## See also

- [ADR 0010: Caller Owns Commit Boundary](0010-caller-owns-commit-boundary.md) — transaction-boundary ownership
- [ADR 0014: Post-Commit Side Effects Only](0014-post-commit-side-effects-only.md) — write safety
