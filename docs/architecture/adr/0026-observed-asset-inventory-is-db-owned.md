# ADR 0026: Observed Asset Inventory Is DB-Owned

## Status

Accepted

## Date

2026-03-16

## Context

IRIS already persists observed market assets in PostgreSQL and seeds the default inventory through migrations.

That means the active asset set is expected to change over time through database-backed operations:

- operators can add or remove assets;
- migrations may seed an initial default set;
- background jobs must process whatever is currently in the database.

Two runtime patterns violated that model:

- a `watched_assets.py` file was still used to repopulate or synchronize observed assets before history backfill jobs;
- a `sources/catalog.py` file introduced a static symbol inventory to decide source fallback chains.

Both patterns create an accidental second source of truth and make runtime behavior depend on files instead of the database.

This conflicts with:

- [ADR 0002](0002-persistence-architecture.md), which makes persisted state authoritative;
- [ADR 0010](0010-caller-owns-commit-boundary.md), which expects explicit write flows instead of hidden runtime mutations;
- [ADR 0022](0022-platform-maturity-additions.md), which requires one source of truth for operational state.

## Decision

The observed asset inventory is owned by the database only.

### Inventory Rules

- the `coins` table is the only runtime source of truth for which assets are observed;
- background jobs must iterate over database rows only and must not import or reconcile assets from Python files;
- asset additions, updates, soft deletes, and reactivation happen only through explicit database-backed service flows and migrations.

### Seeding Rules

- migrations may embed a default seed set for first bootstrapping;
- seed data is historical bootstrap material, not a runtime registry;
- once seeded, runtime behavior must not depend on that file or list remaining present.

### Source-Routing Rules

- market-source fallback order may be defined statically by asset type;
- source adapters may keep their own transport-specific symbol aliases and capability rules;
- a central static inventory of observed symbols per provider must not drive runtime routing.

## Consequences

### Positive

- operators can add or remove observed assets without code edits;
- history jobs and queries stay aligned with actual persisted state;
- runtime no longer has hidden inventory resurrection behavior from Python files;
- provider routing remains explicit without duplicating the observed asset set.

### Negative

- source capability remains distributed across provider adapters instead of one central symbol file;
- adding new default assets now requires either a migration or an explicit create flow, not a file edit;
- debugging source coverage requires checking provider adapters and DB rows separately.

## See also

- [ADR 0002: Persistence Architecture](0002-persistence-architecture.md)
- [ADR 0010: Caller Owns Commit Boundary](0010-caller-owns-commit-boundary.md)
- [ADR 0022: Platform Maturity Additions](0022-platform-maturity-additions.md)
