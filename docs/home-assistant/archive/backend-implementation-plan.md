# Home Assistant Backend Implementation Plan

> Historical implementation plan.
> The agreed backend scope was delivered. Keep this file only as implementation history.

## Goal

Implement an IRIS backend component that:

- receives internal events from the event bus;
- transforms them into an HA-compatible external stream;
- publishes the catalog of available entities, collections, commands, and dashboard schema;
- accepts commands from Home Assistant;
- maintains a bidirectional WebSocket session;
- remains a thin integration layer on top of IRIS domain logic without diluting core domains.

---

## 1. Backend Scope Boundaries

### In Scope

Implement:

- a backend module for HA integration;
- a WebSocket gateway;
- a bridge on top of the existing HA event-bus consumer;
- bootstrap, health, catalog, dashboard, and state endpoints;
- a command-dispatch adapter;
- a runtime-state publisher;
- catalog versioning;
- a dashboard-schema provider;
- operation-update relay;
- catalog-change notifications.

### Out of Scope for This Phase

Do not build yet:

- HA add-on packaging;
- auto-installation of the integration;
- a complex dashboard editor;
- a full UI builder inside control plane;
- entity-per-asset promoted mode;
- a multi-user HA permissions model;
- offline queueing for HA.

---

## 2. Proposed Module Structure

Recommended backend structure:

```text
backend/src/apps/integrations/ha/
  api/
    router.py
    dependencies.py
    schemas.py
  application/
    services.py
    command_dispatcher.py
    catalog_service.py
    dashboard_service.py
    bootstrap_service.py
  bridge/
    event_consumer.py
    event_mapper.py
    event_publisher.py
    websocket_hub.py
    session_manager.py
    state_projector.py
  domain/
    contracts.py
    enums.py
    models.py
  infrastructure/
    repositories.py
    zeroconf.py
  schemas/
    bootstrap.py
    catalog.py
    dashboard.py
    websocket.py
    commands.py
    events.py
```

### Principle

- `api/` — HTTP and WebSocket transport
- `application/` — use-case orchestration
- `bridge/` — event bus to HA external stream linkage
- `schemas/` — dedicated transport contracts
- `domain/` — minimal internal bridge models
- `infrastructure/` — Redis, discovery, and storage integration

---

## 3. Main Backend Components

### 3.1 HA Bridge Module

The HA integration boundary on the backend should have one clear entry point.

It is responsible for:

- protocol export;
- catalog export;
- dashboard-schema export;
- command intake;
- external event publication.

### 3.2 Event Consumer Upgrade

The original Home Assistant consumer only printed events.

It needed to become:

```text
Redis Streams event
  -> HA event mapper
  -> runtime state projector
  -> websocket broadcaster
  -> optional operation relay
```

The upgraded consumer must:

- listen on `iris_events`;
- receive only HA-relevant events;
- normalize payloads;
- update internal HA runtime state;
- broadcast the correct message types to subscribed WebSocket clients.

---

## 4. Event Flow

### 4.1 Incoming Events From the IRIS Bus

Initial minimum set:

- `decision_generated`
- `market_regime_changed`
- `prediction_confirmed`
- `prediction_failed`
- `portfolio_action`
- `portfolio_state_changed`
- `operation_started`
- `operation_progress`
- `operation_completed`
- `operation_failed`

### 4.2 Event Normalization

Use a dedicated mapper:

```text
bridge/event_mapper.py
```

It must:

- accept an internal event envelope;
- convert it into an HA external-protocol message;
- guarantee one stable format regardless of the internal domain source.

### 4.3 Outbound WebSocket Message Types

The bridge must publish:

- `event_emitted`
- `entity_state_changed`
- `state_patch`
- `collection_patch`
- `collection_snapshot`
- `operation_update`
- `catalog_changed`
- `dashboard_changed`
- `system_health`

---

## 5. Runtime State Projection

### Task

The backend needs a layer that builds the “HA-facing view” from internal IRIS events.

This must not be a raw passthrough of internal events.

`state_projector.py` should:

- maintain in-memory runtime state for HA;
- understand paths such as:
  - `system.connection`
  - `portfolio.summary.available_capital`
  - `market.summary.hot_assets_count`
  - `integrations.telegram.auth_status`
- update collections such as:
  - `assets.snapshot`
  - `portfolio.snapshot`
  - `predictions.snapshot`
  - `integrations.snapshot`

### Important

The projector must not become a second domain layer.
It only builds the external projection model.

---

## 6. Entity Catalog

### Goal

IRIS must become the single source of truth for which entities HA may materialize.

### Backend-Owned Catalog

The list of entities must be built in IRIS, not hardcoded inside the HA integration.

### What Belongs in the v1 Catalog

Minimum catalog contents:

- entity definitions;
- collection definitions;
- command definitions;
- dashboard views and widgets;
- compatibility metadata;
- availability and lifecycle metadata.

### Catalog Versioning

The catalog must expose:

- a monotonic `catalog_version`;
- a version change on any change to entities, commands, views, or collections;
- a mechanism for clients to refetch after `catalog_changed`.

---

## 7. Dashboard Schema

The backend should provide a server-driven dashboard schema.

v1 should support:

- a dashboard slug and title;
- views;
- sections;
- widgets;
- collection bindings.

### Not Needed in v1

- a visual editor;
- bidirectional layout editing;
- complex user-authored dashboard composition.

---

## 8. Bootstrap and Health

Expose:

- `GET /api/v1/ha/health`
- `GET /api/v1/ha/bootstrap`

### `/api/v1/ha/health`

Should return:

- basic status;
- backend version;
- protocol version;
- catalog version;
- launch mode;
- whether WebSocket and dashboard support exist.

### `/api/v1/ha/bootstrap`

Should return:

- instance metadata;
- capability flags;
- links to catalog, dashboard, state, and WebSocket endpoints;
- compatibility metadata for HA integration versions.

---

## 9. WebSocket Gateway

### Components

The gateway should include:

- session manager;
- subscription management;
- outbound message queue;
- heartbeat support;
- reconnect-safe resync rules.

### Supported Client Messages

- `hello`
- `subscribe`
- `unsubscribe`
- `command_execute`
- `ping`
- optional `ack_event`

### Supported Server Messages

- `welcome`
- `pong`
- `entity_state_changed`
- `state_patch`
- `collection_snapshot`
- `collection_patch`
- `catalog_changed`
- `dashboard_changed`
- `operation_update`
- `event_emitted`
- `system_health`
- `resync_required`
- `command_ack`

### Failure Semantics and Backpressure

Rules:

- each session owns its outbound queue;
- slow consumers must not block the bridge globally;
- queue overflow should trigger `resync_required`;
- a reconnect must support a full state refresh through `/api/v1/ha/state`.

---

## 10. Command Dispatch

### Goal

Allow Home Assistant to invoke backend commands without turning the backend into a pile of ad-hoc conditional logic.

### Command Routing Strategy

The dispatcher should:

- accept `command_key`;
- validate payload by schema;
- check command availability in the current mode;
- route the command to the correct application service;
- return either immediate acceptance or a typed rejection.

### Operation Integration

Long-running commands should:

- return `command_ack` quickly;
- emit operation lifecycle through `operation_update`;
- use `operation_id` as the stable tracking key.

---

## 11. Relation to Control Plane

### Current-Stage Position

Control plane should govern HA availability policy, but it should not be overloaded with a full HA UI-builder model.

### What Can Be Controlled Now

- whether an entity is enabled by default;
- whether a collection is exposed;
- whether a command is available;
- whether a widget or view is published.

### What Should Not Be Added Yet

- a drag-and-drop HA dashboard editor;
- a dedicated orchestration graph for HA UI behavior.

### Practical v1 Variant

HA catalog output should be configurable from control-plane-backed policy storage.

Control plane sets policy; `catalog_service` builds the final result.

### Policy Precedence Model

Suggested precedence:

1. hard architectural constraints;
2. deployment mode and capability policy;
3. feature flags and rollout configuration;
4. control-plane overrides for availability.

### Observability

Track:

- active sessions;
- outbound queue pressure;
- projector lag;
- resync requests;
- command acceptance and rejection;
- catalog and dashboard refresh events.

---

## 12. Auth / Security

### v1 Solution

v1 may use a bootstrap-issued short-lived session token:

- bootstrap returns `session_token`;
- the client sends it during WebSocket handshake;
- the token has a short lifetime.

### Dev / Local Profile

Local trusted mode may exist for development.

### Important

The code must support future auth-scheme evolution without redesigning the protocol boundary.

---

## 13. State and Storage

### What to Keep in Memory

Safe to keep in memory:

- current entity state;
- collection snapshots;
- operation lifecycle projection;
- session metadata;
- catalog and dashboard versions.

### What Not to Persist Yet

Do not add storage prematurely for:

- historical HA bridge state;
- offline message queues;
- per-session durable snapshots.

Those can be added later only if reconnect or recovery requirements justify them.

---

## 14. Error Handling

Use one explicit error contract for both HTTP and WebSocket boundaries.

### Minimal Error Codes

- `invalid_message`
- `unsupported_protocol_version`
- `unauthorized`
- `forbidden`
- `command_not_available`
- `invalid_payload`
- `catalog_outdated`
- `entity_not_found`
- `operation_not_found`
- `internal_error`

---

## 15. Testing

Must cover:

- consumer reads event -> mapper normalizes -> projector updates state -> hub broadcasts message;
- bootstrap, catalog, dashboard, and state endpoints;
- command dispatch and operation updates;
- reconnect and resync behavior;
- catalog version change and `catalog_changed`;
- compatibility metadata and version checks.

---

## 16. Phased Backend Roadmap

### Phase 1 — Skeleton

- package structure
- API shell
- bridge skeleton

### Phase 2 — Event Bridge

- upgrade current HA consumer
- event mapper
- WebSocket broadcast

### Phase 3 — Catalog

- catalog service
- lifecycle metadata
- versioning

### Phase 4 — Command Bus

- command dispatcher
- command ack
- operation relay

### Phase 5 — Dashboard Schema

- schema generation
- basic dashboard metadata

### Phase 6 — Control-Plane Binding

- policy-backed availability
- catalog gating

### Phase 7 — Hardening

- auth tightening
- reconnect and resync safety
- metrics and diagnostics
- contract tests

---

## 17. Definition of Done

The backend side is considered complete when:

- `/api/v1/ha/health` works;
- `/api/v1/ha/bootstrap` works;
- `/api/v1/ha/catalog` works;
- `/api/v1/ha/dashboard` works;
- `/api/v1/ha/state` works for fast reconnect;
- WebSocket handshake works;
- the event consumer publishes HA-compatible messages;
- the catalog is backend-owned and not duplicated in HA;
- commands can be invoked from HA over WebSocket;
- long-running commands return `operation_id`;
- `catalog_changed` exists;
- entity availability can be controlled through backend policy;
- unit and integration tests cover the boundary;
- the client survives reconnect with correct resync behavior;
- command rejection uses one unified `command_ack/error` format;
- diagnostics and metrics cover session lifecycle and projector lag.

---

## 18. Critical Pitfalls

Do not:

- mix HA bridge code with core domain logic;
- turn collections into a giant sensor transport;
- maintain a hardcoded entity list in both backend and HA;
- let command routing collapse into scattered `if/else` logic;
- overload control plane with HA-specific UI composition too early.

---

## 19. Short Final Decision

The backend should expose a server-driven HA bridge where:

- IRIS owns the protocol, catalog, commands, and dashboard schema;
- Home Assistant acts as a thin runtime client;
- the bridge projects backend truth into an HA-compatible form;
- availability policy can be governed without forking integration logic;
- the whole boundary stays explicit, typed, and observable.
