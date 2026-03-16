# ADR 0025: Runtime Proxy Registry for Public Market Sources

## Status

Accepted

## Date

2026-03-16

## Context

The market-data runtime now depends on several public market sources whose availability is constrained by IP-level throttling and unofficial limits.

This is especially visible on public endpoints such as Yahoo Finance:

- the application can fetch valid history for some assets only intermittently because the primary IP is temporarily rate limited;
- the failure mode is operational, not semantic: the symbol is valid, but the transport path is blocked for a time window;
- we need a way to rotate transport paths without pushing this concern into API contracts, control-plane UI, or database schema.

At the same time, the solution must respect existing architecture constraints:

- [ADR 0011](0011-analytical-engines-never-fetch.md) keeps fetching inside the market-data boundary, not analytical engines;
- [ADR 0013](0013-async-classes-for-orchestration-pure-functions-for-analysis.md) prefers async orchestration services for runtime concerns;
- [ADR 0014](0014-post-commit-side-effects-only.md) means this logic must stay out of request-driven persistence side effects;
- the principal engineering checklist requires explicit ownership, low accidental coupling, and no silent leakage of secrets.

## Decision

The backend uses an internal runtime proxy registry for anonymous public market-source traffic only.

### Source of Truth Rules

- free proxy candidates are fetched from Git-hosted raw lists during runtime bootstrap;
- the imported proxy set is normalized and stored as a JSON registry under the runtime data directory;
- the registry persists health information such as successes, failures, latency, cooldown, and computed rating.

### Boundary Rules

- the proxy registry is internal runtime infrastructure and has no API endpoints, admin forms, or database tables;
- authenticated or key-bearing providers must not use the free proxy registry;
- only public providers that explicitly opt in may route requests through the proxy registry.

### Runtime Rules

- the registry starts as a background task during application lifespan startup;
- startup must not block on proxy probing: the service loads persisted state first and refreshes/probes asynchronously;
- proxy rating is computed from observed success rate, latency, recency, and failure streaks;
- sources may choose one of three modes: `off`, `fallback`, or `preferred`;
- rate limiting is tracked per transport path, so direct traffic and proxied traffic do not share one cooldown bucket.

### Persistence Rules

- proxy state is written to a JSON file in the runtime data directory, not to PostgreSQL;
- the JSON file is the operational cache and restart handoff for proxy health state;
- if Git imports fail, the runtime continues with the last persisted registry or falls back to direct traffic.

## Consequences

### Positive

- public-source fetching can recover from IP-local throttling without changing external API contracts;
- proxy behavior stays inside market-data runtime infrastructure and does not leak into UI or domain models;
- the registry survives restarts and can reuse prior health knowledge instead of re-learning from zero;
- authenticated providers remain isolated from free-proxy risk and do not expose API keys to third-party relays.

### Negative

- runtime complexity increases because transport-path health must now be tracked separately from source identity;
- free proxies are inherently unreliable and can introduce more transient transport noise;
- health scoring is heuristic and requires periodic tuning as source behavior changes;
- debugability becomes harder because request success now depends on both source logic and proxy-path quality.

## See also

- [ADR 0011: Analytical Engines Never Fetch External Data Directly](0011-analytical-engines-never-fetch.md)
- [ADR 0013: Async Classes for Orchestration, Pure Functions for Analysis](0013-async-classes-for-orchestration-pure-functions-for-analysis.md)
- [ADR 0014: Post-Commit Side Effects and Messaging Happen Only After Commit](0014-post-commit-side-effects-only.md)
- [ADR 0023: Documentation Structure and Naming](0023-documentation-structure-and-naming.md)
