# ADR 0029: Frontend Dashboard Live Stream Over Normalized SSE

## Status

Accepted

## Date

2026-03-16

## Context

Frontend currently bootstraps dashboard state through REST snapshots and manual refreshes.
At the same time, backend runtime already publishes internal domain events to Redis Streams.

These internal events are not suitable as a direct frontend contract:

- they expose internal event taxonomy;
- they are too noisy for UI fanout;
- different frontend screens need read-model snapshots, not raw runtime payloads;
- frontend clients must receive broadcast semantics, not worker-style consumer-group delivery.

We need a frontend-facing live channel that can deliver the parts of the system that matter to the UI, while keeping backend internal event routing private.

## Decision

We add a dedicated frontend composition surface under `iris.apps.frontend` that:

- owns frontend-specific REST snapshot aggregation under `/api/v1/frontend/*`;
- exposes Server-Sent Events as the browser-facing transport;
- tails the internal Redis event stream in fanout mode;
- listens only to selected domain events relevant for UI live state;
- translates those internal events into normalized frontend events;
- emits read-model snapshots, not raw runtime events.

The initial normalized frontend event contract is:

- `asset_snapshot_updated`
- `portfolio_snapshot_updated`

The initial frontend snapshot endpoints are:

- `GET /api/v1/frontend/shell`
- `GET /api/v1/frontend/dashboard`
- `GET /api/v1/frontend/stream/dashboard`

`asset_snapshot_updated` carries the current read snapshot for one asset:

- `coin`
- `metrics`
- recent `signals`
- `signal_count`
- current `market_decisions`
- aggregated `coin_market_decision`

`portfolio_snapshot_updated` carries the current read snapshot for portfolio state:

- `state`
- open `positions`
- recent `actions`

The frontend keeps REST snapshot bootstrap from the same `frontend` boundary as the initial load path.
SSE is then used for incremental live patching of the in-memory store.

## Consequences

### Positive

- Frontend receives a stable live contract instead of binding to internal runtime events.
- UI stays near-real-time without full dashboard reloads.
- Internal event taxonomy can evolve independently from frontend event names.
- SSE remains simple for browsers and works well with one-way dashboard updates.

### Negative

- Backend now owns an explicit translation layer from internal events to frontend snapshots.
- Some updates will query read models on demand, which adds extra database work.
- REST snapshot and SSE patching must stay schema-compatible.

## See also

- [0001-event-driven-runtime.md](0001-event-driven-runtime.md)
- [0005-analytical-snapshot-api-semantics.md](0005-analytical-snapshot-api-semantics.md)
- [0024-frontend-dashboard-composition-and-route-bootstrapping.md](0024-frontend-dashboard-composition-and-route-bootstrapping.md)
