# IRIS Event Control Plane Migration Plan

## Purpose

This document captures the current event runtime, the routing logic that must be migrated, and the staged implementation plan for introducing a DB-backed Event Control Plane without breaking the existing Redis-stream-driven pipeline.

## Current Runtime Topology

### Transport

- Domain producers publish into a single Redis stream through [`backend/src/runtime/streams/publisher.py`](../backend/src/runtime/streams/publisher.py).
- Events are serialized as `IrisEvent` envelopes in [`backend/src/runtime/streams/types.py`](../backend/src/runtime/streams/types.py).
- Worker processes are spawned during backend lifespan startup in [`backend/src/core/bootstrap/lifespan.py`](../backend/src/core/bootstrap/lifespan.py).
- Each worker group reads the same stream and filters messages locally.

### Current Source Of Truth

The effective routing topology is currently split across code:

- worker subscription matrix in [`backend/src/runtime/streams/router.py`](../backend/src/runtime/streams/router.py)
- consumer instantiation and handler binding in [`backend/src/runtime/streams/workers.py`](../backend/src/runtime/streams/workers.py)
- handler-level event guards inside consumer classes such as:
  - [`backend/src/apps/anomalies/consumers/candle_anomaly_consumer.py`](../backend/src/apps/anomalies/consumers/candle_anomaly_consumer.py)
  - [`backend/src/apps/anomalies/consumers/sector_anomaly_consumer.py`](../backend/src/apps/anomalies/consumers/sector_anomaly_consumer.py)
  - [`backend/src/apps/news/consumers.py`](../backend/src/apps/news/consumers.py)
  - [`backend/src/apps/hypothesis_engine/consumers/hypothesis_consumer.py`](../backend/src/apps/hypothesis_engine/consumers/hypothesis_consumer.py)
- consumer-specific compatibility constants such as [`backend/src/apps/hypothesis_engine/constants.py`](../backend/src/apps/hypothesis_engine/constants.py)

This means IRIS already has a topology, but it is not declarative, not auditable, and not editable at runtime.

## Current Event Flows

### Primary Market Analysis Flow

1. `market_data` publishes `candle_inserted` and `candle_closed`.
2. `indicator_workers` react to `candle_closed` and publish `indicator_updated`.
3. `analysis_scheduler_workers` react to `indicator_updated` and publish `analysis_requested`.
4. `pattern_workers` react to `analysis_requested` and publish:
   - `pattern_detected`
   - `pattern_cluster_detected`
   - `signal_created`
5. `regime_workers` react to `indicator_updated` and publish:
   - `market_regime_changed`
   - `market_cycle_changed`
6. `decision_workers` react to:
   - `pattern_detected`
   - `pattern_cluster_detected`
   - `market_regime_changed`
   - `market_cycle_changed`
   - `signal_created`
7. `decision_workers` publish `decision_generated`.
8. `signal_fusion_workers` react to:
   - `pattern_detected`
   - `signal_created`
   - `market_regime_changed`
   - `correlation_updated`
   - `news_symbol_correlation_updated`
9. `portfolio_workers` react to:
   - `decision_generated`
   - `market_regime_changed`
   - `portfolio_balance_updated`
   - `portfolio_position_changed`

### Cross-Domain Auxiliary Flows

- `cross_market_workers` react to `candle_closed` and `indicator_updated`, then publish `correlation_updated`, `market_leader_detected`, and prediction-related events.
- `anomaly_workers` react to `candle_closed`, then publish `anomaly_detected`.
- `anomaly_sector_workers` react to `anomaly_detected` and enqueue enrichment / sector scans.
- `news_normalization_workers` react to `news_item_ingested` and publish `news_item_normalized`.
- `news_correlation_workers` react to `news_item_normalized` and publish `news_symbol_correlation_updated`.
- `hypothesis_workers` optionally react to:
  - `signal_created`
  - `anomaly_detected`
  - `decision_generated`
  - `market_regime_changed`
  - `portfolio_position_changed`
  - `portfolio_balance_updated`

### Non-routed Event Consumers

Some read paths inspect Redis streams directly and are not part of the consumer routing graph:

- hypothesis SSE in [`backend/src/apps/hypothesis_engine/views.py`](../backend/src/apps/hypothesis_engine/views.py)
- indicator market radar / flow projections in [`backend/src/apps/indicators/services.py`](../backend/src/apps/indicators/services.py)

These are observers, not runtime consumers, and should remain outside route delivery while still using the event stream as an observability source.

## Current Producer Inventory

Current producers live in domain services and workers, including:

- `market_data`
- `runtime.streams.workers`
- `patterns.domain.success`
- `cross_market.engine`
- `anomalies.services.anomaly_service`
- `news.pipeline`
- `portfolio.engine`
- `portfolio.services`
- `market_structure.services`
- `hypothesis_engine.services`
- `predictions.engine`

The control plane must not require producer rewrites to new APIs on day one. Existing `publish_event(...)` calls must remain valid while event metadata is enriched behind the transport boundary.

## Logic To Migrate

The following hardcoded logic must move into the new control-plane model:

- `WORKER_EVENT_TYPES` in [`backend/src/runtime/streams/router.py`](../backend/src/runtime/streams/router.py)
- worker-group to handler mapping in `create_worker(...)`
- hypothesis compatibility matrix in `SUPPORTED_HYPOTHESIS_SOURCE_EVENTS`
- implicit route semantics encoded by per-consumer `if event.event_type != ...: return`
- event topology documentation currently scattered across worker code

The following logic stays in code but becomes runtime implementation behind registered consumers:

- domain-specific handler behavior in the current consumer classes and worker handlers
- producer payload creation
- downstream business side effects inside domain services

## Integration Points

### Storage

- Alembic migrations under [`backend/src/migrations/versions`](../backend/src/migrations/versions)
- SQLAlchemy declarative models under `backend/src/apps/*/models.py`

### Runtime

- ingress event publisher in [`backend/src/runtime/streams/publisher.py`](../backend/src/runtime/streams/publisher.py)
- stream parsing in [`backend/src/runtime/streams/types.py`](../backend/src/runtime/streams/types.py)
- worker orchestration in [`backend/src/runtime/streams/runner.py`](../backend/src/runtime/streams/runner.py)
- lifespan bootstrap in [`backend/src/core/bootstrap/lifespan.py`](../backend/src/core/bootstrap/lifespan.py)

### API

- FastAPI router registration in [`backend/src/core/bootstrap/app.py`](../backend/src/core/bootstrap/app.py)
- existing view/schema patterns in `backend/src/apps/*/views.py` and `backend/src/apps/*/schemas.py`

### Frontend

- Vue router in [`frontend/src/router/index.ts`](../frontend/src/router/index.ts)
- HTTP client / contracts in [`frontend/src/services/api.ts`](../frontend/src/services/api.ts)

## Risks In Current State

- Route changes require code edits and deploys.
- Runtime routing is not auditable.
- No draft/apply workflow exists.
- No route-level mute, pause, shadow, or throttle exists.
- Compatibility rules are duplicated between router code and consumer guards.
- Event metadata is too thin for topology-aware filtering.
- Worker groups read the entire stream and discard irrelevant events locally.

## Target Architecture

### Control Plane Boundaries

- `apps/control_plane/models.py`
  - `EventDefinition`
  - `EventConsumer`
  - `EventRoute`
  - `EventRouteAuditLog`
  - `TopologyConfigVersion`
  - `TopologyDraft`
  - `TopologyDraftChange`
- `apps/control_plane/repositories.py`
- `apps/control_plane/services.py`
- `apps/control_plane/cache.py`
- `apps/control_plane/dispatcher.py`
- `apps/control_plane/views.py`
- `apps/control_plane/schemas.py`

### Runtime Shape

1. Producers keep publishing to one ingress stream.
2. A dedicated topology dispatcher consumes ingress events.
3. The dispatcher evaluates routes from a hot topology snapshot loaded from cache.
4. Matched deliveries are fanned out into per-consumer delivery streams.
5. Consumer workers process only their delivery stream.
6. Control events refresh the topology cache and broadcast version bumps.

This removes route evaluation from worker code while preserving the current handler implementations.

## Planned Migration Path

### Stage 1

- Document current topology and migration path.
- Freeze the current hardcoded routing map as the bootstrap source.

### Stage 2

- Add control-plane models, enums, migrations, and initial seed data.
- Seed current event definitions, consumers, and routes from the hardcoded topology.

### Stage 3

- Add repositories and application services for topology CRUD, drafts, and audit.

### Stage 4

- Introduce the runtime dispatcher and route evaluator.
- Keep existing consumer handler code, but move routing decisions to the dispatcher.

### Stage 5

- Add topology snapshot caching, version bump refresh, and control-event invalidation.

### Stage 6

- Expose registry, routes, topology graph, drafts, apply/discard, and observability APIs.

### Stage 7

- Add draft/apply workflow with topology version snapshots and diffs.

### Stage 8

- Add a basic topology UI with palette, canvas, inspector, and drag-and-drop route editing against draft changes.

### Stage 9

- Update README, architecture docs, and changelog so the control plane becomes the documented source of truth.

## Migration Acceptance Criteria

- Existing producers keep publishing without API breakage.
- Existing domain handlers remain reusable through registered consumers.
- Initial DB topology exactly mirrors the current hardcoded routing map.
- New route management becomes the source of truth for runtime delivery.
- No runtime SQL lookup is required for each event delivery decision.
