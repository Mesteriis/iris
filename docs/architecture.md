# IRIS Architecture

## Scope

IRIS is an event-driven market intelligence service. The current codebase includes:

- `coins`
- `candles`
- indicators and market regime
- pattern detection and signal generation
- signal fusion and decisions
- portfolio state and exchange sync
- cross-market intelligence and predictions
- anomaly detection
- news normalization and correlation
- market structure ingestion
- optional hypothesis engine
- Home Assistant integration

## Backend runtime

The backend owns three concerns inside one service:

- FastAPI HTTP API
- SQLAlchemy/Alembic database access and migrations
- TaskIQ brokers plus dedicated worker processes
- Redis Streams based event transport

FastAPI only enqueues TaskIQ jobs. Task execution runs in dedicated worker processes started from the backend lifespan hook, so long-running analytics never execute inside the main HTTP event loop.

Background tasks:

- startup bootstrap task: sync watched assets and backfill retention windows from seed data
- periodic refresh task: append newly available bars for enabled, non-deleted assets
- scheduler-triggered domain jobs for pattern statistics, market structure health, portfolio sync, prediction evaluation, news polling and hypothesis evaluation

The default `source` is an internal deterministic market-data generator for the MVP, so the project runs without external API keys.

## Event Runtime

The event runtime currently uses a single ingress Redis stream for domain events.

Producers publish through `runtime/streams/publisher.py`.

Worker processes are spawned from the backend lifespan hook and currently implement domain behavior for:

- indicators
- analysis scheduling
- patterns
- regime updates
- decisions
- signal fusion
- cross-market intelligence
- anomaly detection
- news normalization and correlation
- portfolio reactions
- optional hypothesis generation

## Event Control Plane

IRIS now includes a DB-backed Event Control Plane storage layer. The runtime cutover happens in subsequent stages, but the topology source of truth already exists in the schema and is seeded from the current hardcoded routing graph.

Control-plane entities:

- `event_definitions`
- `event_consumers`
- `event_routes`
- `event_route_audit_logs`
- `topology_config_versions`
- `topology_drafts`
- `topology_draft_changes`

The initial published topology is generated from the current worker subscription map so the migration path stays backward-compatible.

The control-plane application layer now includes repositories and services for:

- event and consumer registry reads
- route create/update/status changes with audit logging
- topology snapshot assembly
- draft storage and preview diffs before publish
- topology graph assembly for visual editors
- observability projections backed by Redis metrics plus DB topology state

The runtime side now also has a dedicated dispatcher/evaluator layer that can consume a topology snapshot and decide delivery based on:

- compatibility contracts
- route status (`active`, `muted`, `paused`, `throttled`, `shadow`, `disabled`)
- scope matching
- route filters
- throttle windows
- shadow observe-only behavior

Topology snapshots are now loaded through a dedicated cache manager:

- DB remains the source of truth
- Redis stores the hot serialized topology snapshot
- the runtime keeps an in-process snapshot copy
- control events trigger cache refresh/invalidation
- downstream domain workers now consume per-consumer delivery streams instead of filtering the ingress stream locally

The HTTP surface now exposes the control plane as a first-class backend boundary:

- `/control-plane/registry/*` for event and consumer registry reads plus compatibility discovery
- `/control-plane/routes*` for route CRUD/status mutations guarded by observe/control mode headers
- `/control-plane/topology/snapshot` and `/control-plane/topology/graph` for canvas/inspector data
- `/control-plane/drafts*` for draft creation, staged route changes and diff previews
- `/control-plane/drafts/{id}/apply` and `/control-plane/drafts/{id}/discard` for lifecycle transitions
- `/control-plane/audit` for route audit history
- `/control-plane/observability` for route/consumer throughput, failure, latency, lag and dead-consumer state

The frontend now includes a first-party control-plane workbench at `/control-plane`:

- graph/canvas view reads the published topology from `/control-plane/topology/graph`
- palette uses event and consumer nodes from the graph payload rather than UI-hardcoded wiring
- drag-and-drop from event node to consumer node stages a `route_created` draft change
- inspector stages `route_status_changed` draft changes for selected live edges
- apply/discard are explicit UI actions against the draft lifecycle endpoints
- the canvas edits declarative route rules and draft changes only; it does not execute any visual low-code graph at runtime

Control mode protection currently uses request headers:

- `X-IRIS-Actor`
- `X-IRIS-Access-Mode: observe|control`
- optional `X-IRIS-Reason`
- optional `X-IRIS-Control-Token` when `IRIS_CONTROL_TOKEN` is configured

Observability is now split across two layers:

- dispatcher metrics track route evaluations/deliveries/shadow counts
- delivery workers emit consumer success/failure heartbeats keyed by `consumer_key` and `route_key`

Draft publish semantics are now explicit:

- each draft is pinned to the latest published topology version at creation time
- apply is rejected for stale drafts, preventing silent overwrite of a newer published topology
- apply creates a new `topology_config_versions` row, snapshots the resulting graph and marks the draft as `applied`
- discard leaves live routes untouched, marks the draft as `discarded` and still records discard audit rows for traceability
- publish emits `control.topology_published` plus `control.cache_invalidated`, making the new version the runtime source of truth

## Database

The database includes the market-data core plus higher-level analytical domains. Key persisted areas now include:

- asset and candle history
- indicator caches and regime snapshots
- signals, decisions and backtests
- portfolio balances, positions and actions
- cross-market relations and prediction memory
- anomaly entities
- news sources, items and symbol links
- market-structure sources and snapshots
- hypothesis prompts, hypotheses, evaluations and weights
- event control-plane topology and audit metadata

## Home Assistant

The custom integration polls `GET /status` and exposes `sensor.iris_status`.

The addon runs the same backend code path as Docker/systemd deployments, so Home Assistant also uses the single-service backend model.

## Deletion

Deleting a coin removes its history immediately and marks the coin as deleted in `coins`, which prevents startup seed sync from recreating it on the next restart.
