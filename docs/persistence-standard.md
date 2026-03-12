# IRIS Persistence Standard

Date: 2026-03-12

## Goal

IRIS persistence must be explicit, typed, async-first, observable, and safe against accidental lazy loading or hidden transaction ownership.

## Layering

### Repository Layer

Purpose:

- write-side persistence
- aggregate loading
- explicit `get_for_update(...)`
- `add(...)`, `save(...)`, `delete(...)`, `exists(...)`

Rules:

- repositories may return mutable ORM entities only on explicit write contracts.
- repositories may call `flush()` when required for generated IDs, locks, or write sequencing.
- repositories must not call `commit()` or `rollback()`.
- repository methods must log entry, mode, entity, and important selection parameters.

### Query Services

Purpose:

- read-only list/detail/table/dashboard flows
- explicit projections
- immutable read models
- anti-N+1 eager loading or Core projections

Rules:

- query services return immutable typed read models by default.
- query services never call `commit()`.
- query services must not leak session-bound ORM entities to callers.
- list/detail APIs should consume query services directly rather than raw sessions.

### Unit of Work

Purpose:

- own transaction boundaries
- expose `commit()`, `rollback()`, `flush()`
- centralize transaction lifecycle logging

Rules:

- HTTP command handlers, workers, and scheduled jobs create a unit of work.
- application services coordinate repositories/query services using the same unit of work session.
- on scope exit without explicit commit, the unit of work rolls back any open transaction.

## Read/Write Contract Policy

### Read Path

Default return type:

- `@dataclass(frozen=True, slots=True)` read models

Policy:

- caller receives fully materialized data.
- no hidden lazy loading after return.
- JSON-like fields should be normalized into immutable containers where practical.

Naming:

- `get_read_by_id(...)`
- `list_recent(...)`
- `fetch_page(...)`
- `get_detail(...)`

### Write Path

Default return type:

- mutable ORM entity or explicit write-state object

Policy:

- write methods must be explicit about mutability.
- use names like `get_for_update(...)`, `load_mutable(...)`, `list_due_for_update(...)`.

## ORM / SQLAlchemy Core / Raw SQL Policy

### ORM

Use for:

- standard CRUD
- aggregate/entity loading
- explicit eager relation loading

### SQLAlchemy Core

Use for:

- projections
- joins that are clearer as Core statements
- bulk updates/inserts/upserts
- CTE/window-function style reads

### Raw SQL

Allowed only when one of these is true:

- vendor-specific behavior makes Core meaningfully worse
- dynamic object names are unavoidable and isolated in infrastructure code
- SQL is still bounded, tested, and documented

Current accepted exception zone:

- Timescale continuous aggregate maintenance and dynamic aggregate-view access in `apps/market_data`

## Anti-N+1 Policy

N+1 is a defect, not an optimization backlog.

Required practices:

- eager loading through `selectinload` / `joinedload` where ORM is used
- projection queries for list/detail responses
- loading profile parameters when multiple materialization shapes are legitimate
- no caller-side relation access after returning from persistence layer

Loading-profile naming:

- `base`
- `with_relations`
- `full`

## Logging Policy

Shared logger namespace:

- `iris.persistence`

Minimum events:

- repository/query method entry
- read/write mode
- entity/domain name
- loading profile
- row counts for list queries
- transaction `begin`, `flush`, `commit`, `rollback`
- raw SQL exception or fallback path
- lock/select-for-update path
- DB failure with safe context

Sensitive data handling:

- never log secrets, tokens, session strings, or provider credentials
- avoid dumping entire payloads; log identifiers, counts, and safe filters only

## Suggested Code Structure

```text
backend/src/
  core/db/
    session.py
    uow.py
    persistence.py
  apps/<domain>/
    repositories.py
    query_services.py
    read_models.py
    services.py
    views.py
```

Notes:

- tiny domains may keep repository/query service in one file if the boundary remains clear.
- large service files should be split by responsibility instead of introducing a single god service.

## Migration Rules

1. Move direct route/service/task DB access behind repository or query service.
2. Keep behavior backward-compatible at the HTTP and event-contract level.
3. Replace raw SQL with Core unless it is a documented exception.
4. Introduce immutable read models before exposing new read boundaries.
5. Add tests for behavior parity, transaction boundaries, and read-model safety.
6. Update audit/doc/changelog alongside code, not afterward.

## Implementation Status

Initial rollout completed in this refactor pass:

- shared persistence foundation under `core/db`:
  - explicit async unit of work
  - session-wrapping unit of work for tests and externally managed sessions
  - shared persistence logger helpers
- migrated domains currently covered by the standard:
  - `apps/hypothesis_engine`
  - `apps/control_plane`
  - `apps/news`
  - `apps/market_structure`
  - repository/query split
  - immutable read models for read paths
  - centralized transaction ownership in services/tasks/views/consumers
  - persistence logging hooks

Remaining domains are tracked in [docs/persistence-audit.md](/Users/avm/projects/Personal/iris/docs/persistence-audit.md).
