# IRIS ↔ Home Assistant Protocol Specification

## Status

**Draft v1**

> **Document Status**
>
> This document is normative for IRIS ↔ Home Assistant protocol v1.
>
> **Related implementation history:**
> - [Home Assistant Archive](archive/index.md) — completed implementation plans, backlog, and rollout tracker
> - [Integration Architecture Note](notes/integration-architecture.md) — architecture overview and explanatory note
>
> If any derived document conflicts with this spec, this spec wins.

## Goal

Define a stable contract between the IRIS backend and the Home Assistant custom integration so that:

- IRIS remains the only source of truth for the entity catalog, command catalog, dashboard schema, and runtime state;
- the HA integration remains a thin adapter rather than a second backend;
- new entities, commands, and view models can be added without manually synchronizing code in two places;
- bidirectional communication works through a push-based event-driven model rather than polling as the primary mechanism;
- the contract can evolve without breaking existing installations.

---

## 1. Architectural Model

### 1.1 Roles

#### IRIS

**Owns:**

- runtime state
- domain events
- entity catalog
- collection catalog
- command catalog
- dashboard schema
- operation lifecycle
- capability matrix

#### Home Assistant Integration

**Is responsible for:**

- discovery and pairing
- WebSocket session
- entity materialization in HA
- local runtime store
- sending commands to IRIS
- applying dashboard schema in HA
- user-local overrides

---

## 2. Transport

### 2.1 Discovery

Discovery is performed through zeroconf / mDNS.

**Service type:**

```text
_iris._tcp.local.
```

**Required TXT records**

- `instance_id`
- `version`
- `api_port`
- `ws_path`
- `mode`
- `catalog_version`
- `protocol_version`

**Recommended TXT records**

- `requires_auth`
- `display_name`
- `dashboard_supported`
- `commands_supported`

### 2.2 HTTP API

HTTP is used for:

- initial bootstrap
- catalog and dashboard-schema retrieval
- fallback read endpoints
- health checks
- optional operation inspection

### 2.3 WebSocket

WebSocket is the primary live transport for:

- runtime updates
- catalog changes
- command execution
- operation tracking
- collection patches

**Main endpoint:**

```text
/api/v1/ha/ws
```

---

## 3. Protocol Principles

### 3.1 Server-Driven Integration

IRIS always declares what is available for HA:

- which entities can be created
- which collections exist
- which commands can be called
- which views should be displayed

HA must not hardcode the entity catalog as its source of truth.

### 3.2 Not Everything Is an Entity

The protocol separates:

- **entities** — materializable HA objects
- **collections** — large aggregated data sets
- **commands** — callable actions
- **views** — UI and dashboard schema

### 3.3 Backward Compatibility

All contracts must support versioning and soft evolution:

- new fields may be added
- field removal is allowed only through a deprecation lifecycle
- entities must not disappear abruptly without a migration path
- command renames must carry replacement metadata

---

## 4. HTTP Endpoints

### 4.1 Health

```text
GET /api/v1/ha/health
```

**Purpose:**

- initial liveness check
- protocol-compatibility check
- bridge-state check

**Example response:**

```json
{
  "status": "ok",
  "instance_id": "iris-main-001",
  "version": "2026.03.14",
  "protocol_version": 1,
  "catalog_version": "2026.03.14",
  "mode": "full",
  "websocket_supported": true,
  "dashboard_supported": true
}
```

### 4.2 Bootstrap

```text
GET /api/v1/ha/bootstrap
```

**Purpose:**

- a single starting point for the integration
- avoids making five separate requests during initial connection

**Example response:**

```json
{
  "instance": {
    "instance_id": "iris-main-001",
    "display_name": "IRIS Main",
    "version": "2026.03.14",
    "protocol_version": 1,
    "catalog_version": "2026.03.14",
    "mode": "full",
    "minimum_ha_integration_version": "0.1.0",
    "recommended_ha_integration_version": "0.1.0"
  },
  "capabilities": {
    "dashboard": true,
    "commands": true,
    "collections": true,
    "promoted_entities": false
  },
  "catalog_url": "/api/v1/ha/catalog",
  "dashboard_url": "/api/v1/ha/dashboard",
  "ws_url": "/api/v1/ha/ws"
}
```

**URL Resolution:**

All URLs in the bootstrap response are **relative to the origin of the bootstrap request**. Clients MUST resolve them against the bootstrap endpoint origin (scheme + host + port).

### 4.3 Catalog

```text
GET /api/v1/ha/catalog
```

**Purpose:**

- describe available entities
- describe collections
- describe commands
- describe lifecycle and compatibility metadata

**Example response:**

```json
{
  "catalog_version": "2026.03.14",
  "protocol_version": 1,
  "mode": "full",
  "entities": [],
  "collections": [],
  "commands": [],
  "views": []
}
```

### 4.4 Dashboard Schema

```text
GET /api/v1/ha/dashboard
```

**Purpose:**

- server-driven dashboard, layout, card, and view schema

**Example response:**

```json
{
  "version": 1,
  "slug": "iris",
  "title": "IRIS",
  "views": []
}
```

### 4.5 Optional Operation Status

```text
GET /api/v1/ha/operations/{operation_id}
```

**Purpose:**

- fallback or debug read for an operation

**Example response:**

```json
{
  "operation_id": "op_123",
  "status": "completed",
  "result": {
    "message": "Asset added"
  }
}
```

### 4.6 State Snapshot (for Fast Reconnect)

```text
GET /api/v1/ha/state
```

**Purpose:**

- fast reconnect recovery
- authoritative full-state snapshot

**Example response:**

```json
{
  "projection_epoch": "2026.03.14-001",
  "sequence": 142,
  "entities": {
    "system.connection": {
      "state": true,
      "attributes": {}
    }
  },
  "collections": {
    "assets.snapshot": {},
    "portfolio.snapshot": {}
  }
}
```

---

## 5. Catalog Schema

### 5.1 Top-Level Structure

```json
{
  "catalog_version": "2026.03.14",
  "protocol_version": 1,
  "mode": "full",
  "entities": [],
  "collections": [],
  "commands": [],
  "views": []
}
```

### 5.2 Entity Definition

**Required fields**

- `entity_key`
- `platform`
- `name`
- `state_source`

**Recommended fields**

- `command_key`
- `icon`
- `category`
- `default_enabled`
- `availability`
- `since_version`
- `deprecated_since`
- `replacement`
- `entity_registry_enabled_default`
- `device_class`
- `unit_of_measurement`

`command_key` SHOULD be used for control-capable entity definitions (`button`, `switch`, `select`) when the entity is a UI projection of a backend command rather than a purely state-owned entity. If the field is absent, the client MAY use `entity_key` as an implicit command identifier for control entities.

**Example:**

```json
{
  "entity_key": "system.connection",
  "platform": "binary_sensor",
  "name": "IRIS Connection",
  "state_source": "system.connection",
  "icon": "mdi:lan-connect",
  "category": "diagnostic",
  "default_enabled": true,
  "device_class": "connectivity",
  "since_version": "2026.03.14",
  "deprecated_since": null,
  "replacement": null
}
```

**Example control-bound entity:**

```json
{
  "entity_key": "actions.portfolio_sync",
  "platform": "button",
  "name": "Portfolio Sync",
  "state_source": "actions.portfolio_sync",
  "command_key": "portfolio.sync",
  "icon": "mdi:sync",
  "category": "config",
  "since_version": "2026.03.15"
}
```

### 5.3 Supported HA Platforms

v1 supports:

- `sensor`
- `binary_sensor`
- `switch`
- `button`
- `select`
- `number`
- `event`

Extending the list later is allowed only through a protocol bump or capability flag.

### 5.4 Entity Availability

**Example:**

```json
{
  "modes": ["full", "local", "ha_addon"],
  "requires_features": ["portfolio"],
  "status": "active"
}
```

Where:

- **modes** — the launch modes in which the entity is allowed
- **requires_features** — the domain capabilities that must be enabled
- **status** — `active | deprecated | hidden | removed`

### 5.5 Collection Definition

A collection is not an HA entity. It is a runtime data model for UI and store usage.

**Required fields:**

- `collection_key`
- `kind`
- `transport`

**Example:**

```json
{
  "collection_key": "assets.snapshot",
  "kind": "mapping",
  "transport": "websocket",
  "dashboard_only": true,
  "since_version": "2026.03.14"
}
```

**Possible `kind` values:**

- `mapping`
- `list`
- `table`
- `timeline`
- `summary`

### 5.6 Command Definition

**Required fields:**

- `command_key`
- `name`
- `kind`

**Recommended fields:**

- `input_schema`
- `returns`
- `availability`
- `since_version`
- `deprecated_since`
- `replacement`

**Example:**

```json
{
  "command_key": "asset.add",
  "name": "Add Asset",
  "kind": "action",
  "input_schema": {
    "type": "object",
    "properties": {
      "symbol": {
        "type": "string"
      }
    },
    "required": ["symbol"]
  },
  "returns": "operation",
  "since_version": "2026.03.14"
}
```

**Possible `kind` values:**

- `action`
- `flow`
- `toggle`
- `selection`
- `refresh`
- `admin`

### 5.7 View Definition

A view is a server-declared dashboard fragment.

**Example:**

```json
{
  "view_key": "overview",
  "title": "Overview",
  "kind": "dashboard_view",
  "sections": [
    {
      "section_key": "market_summary",
      "title": "Market Summary",
      "widgets": [
        {
          "widget_key": "hot_assets",
          "kind": "table",
          "source": "assets.snapshot"
        }
      ]
    }
  ]
}
```

---

## 6. Runtime State Model

### 6.1 State-Source Convention

The `state_source` field in an entity definition points to a path in runtime state.

**Example:**

```text
system.connection
portfolio.summary.available_capital
market.summary.hot_assets_count
settings.default_timeframe
```

### 6.2 Collection-Source Convention

Collections are updated either through full snapshots or patch messages.

---

## 7. WebSocket Protocol

### 7.1 Session Lifecycle

#### Stage 1 — Connect

HA opens a WebSocket:

```text
ws://host:port/api/v1/ha/ws
```

#### Stage 2 — Hello

HA sends a hello message.

**Example:**

```json
{
  "type": "hello",
  "protocol_version": 1,
  "client": {
    "name": "home_assistant",
    "version": "1.0.0"
  },
  "instance_id": "optional-known-instance-id"
}
```

#### Stage 3 — Welcome

IRIS returns welcome.

**Example:**

```json
{
  "type": "welcome",
  "protocol_version": 1,
  "instance": {
    "instance_id": "iris-main-001",
    "version": "2026.03.14",
    "mode": "full",
    "catalog_version": "2026.03.14"
  },
  "capabilities": {
    "commands": true,
    "collections": true,
    "dashboard": true
  }
}
```

#### Stage 4 — Subscribe

HA sends the list of streams it cares about.

**Example:**

```json
{
  "type": "subscribe",
  "entities": ["*"],
  "collections": ["assets.snapshot", "portfolio.snapshot"],
  "operations": true,
  "catalog": true,
  "dashboard": true
}
```

### 7.2 Client -> Server Messages

#### `hello`

Establishes the session.

#### `subscribe`

Subscribes to changes.

#### `unsubscribe`

Removes subscriptions.

**Example:**

```json
{
  "type": "unsubscribe",
  "collections": ["assets.snapshot"]
}
```

#### `command_execute`

Executes a command.

**Example:**

```json
{
  "type": "command_execute",
  "command": "asset.add",
  "payload": {
    "symbol": "BTC"
  },
  "request_id": "req_001"
}
```

#### `ping`

**Example:**

```json
{
  "type": "ping",
  "timestamp": "2026-03-14T10:00:00Z"
}
```

#### `ack_event`

Optional client acknowledgement.

### 7.3 Server -> Client Messages

#### `welcome`

Response to `hello`.

#### `pong`

Response to `ping`.

#### `entity_state_changed`

State change for an entity.

**Example:**

```json
{
  "type": "entity_state_changed",
  "entity_key": "system.connection",
  "state": true,
  "attributes": {
    "last_seen": "2026-03-14T10:00:05Z"
  },
  "timestamp": "2026-03-14T10:00:05Z"
}
```

#### `state_patch`

Patch on runtime state.

**Example:**

```json
{
  "type": "state_patch",
  "path": "portfolio.summary.available_capital",
  "value": 12450.75,
  "timestamp": "2026-03-14T10:00:10Z"
}
```

#### `collection_snapshot`

Full collection snapshot.

```json
{
  "type": "collection_snapshot",
  "collection_key": "assets.snapshot",
  "data": {
    "BTC": {
      "decision": "BUY",
      "confidence": 0.82
    }
  },
  "timestamp": "2026-03-14T10:00:12Z"
}
```

#### `collection_patch`

Partial collection update.

```json
{
  "type": "collection_patch",
  "collection_key": "assets.snapshot",
  "op": "upsert",
  "path": "BTC",
  "value": {
    "decision": "STRONG_BUY",
    "confidence": 0.91
  },
  "timestamp": "2026-03-14T10:00:15Z"
}
```

#### `catalog_changed`

Signals that the client must refetch the catalog.

```json
{
  "type": "catalog_changed",
  "catalog_version": "2026.03.15",
  "timestamp": "2026-03-14T10:00:20Z"
}
```

#### `dashboard_changed`

Signals that the client must refetch the dashboard schema.

#### `operation_update`

Operation-state update.

```json
{
  "type": "operation_update",
  "operation_id": "op_123",
  "command": "portfolio.sync",
  "operation_type": "portfolio.sync",
  "status": "in_progress",
  "message": "Synchronizing portfolio",
  "timestamp": "2026-03-14T10:00:30Z"
}
```

#### `resync_required`

The server signals that the client must immediately perform a full resync and reopen the WebSocket session.

Used for backend-detected delivery failures, for example when the outbound session queue overflows.

```json
{
  "type": "resync_required",
  "reason": "queue_overflow",
  "state_url": "/api/v1/ha/state",
  "message": "Outbound session queue overflowed. Client must perform a full state resync."
}
```

#### `event_emitted`

Domain-oriented notification for HA events. Uses the full event envelope.

```json
{
  "type": "event_emitted",
  "event_type": "decision_generated",
  "event_id": "evt_001",
  "source": "decision_engine",
  "payload": {
    "coin": "BTC",
    "decision": "BUY",
    "confidence": 0.82
  },
  "timestamp": "2026-03-14T10:00:40Z"
}
```

#### `system_health`

Technical bridge and runtime status.

#### `command_ack`

Response to `command_execute`.

**Positive ack:**

```json
{
  "type": "command_ack",
  "request_id": "req_002",
  "operation_id": "op_456",
  "accepted": true
}
```

**Negative ack:**

```json
{
  "type": "command_ack",
  "request_id": "req_002",
  "accepted": false,
  "error": {
    "code": "command_not_available",
    "message": "Command is not available in current mode",
    "details": {
      "command": "portfolio.sync",
      "mode": "local"
    }
  },
  "retryable": false
}
```

### 7.x Delivery and Resynchronization Semantics

All state-bearing WebSocket messages MUST include:

- `projection_epoch`: string (monotonic version identifier)
- `sequence`: integer (monotonic within the epoch)

**State-bearing messages:**

- `entity_state_changed`
- `state_patch`
- `collection_snapshot`
- `collection_patch`
- `catalog_changed`
- `dashboard_changed`
- `operation_update`
- `system_health`

**Rules:**

- `sequence` is strictly monotonic within a `projection_epoch`
- the client MUST detect sequence gaps
- if a gap is detected, or if `projection_epoch` changes, the client MUST trigger a full resync
- a full resync MUST use `/api/v1/ha/state` or refetch bootstrap + catalog + the required collections, depending on capability
- `resync_required` is a control message and does not participate in `sequence` monotonicity; after receiving it, the client MUST refresh state and reconnect

---

## 8. Event Envelope

All runtime events delivered into HA must use a single envelope.

```json
{
  "event_type": "decision_generated",
  "event_id": "evt_001",
  "source": "decision_engine",
  "timestamp": "2026-03-14T10:00:40Z",
  "payload": {}
}
```

**Required fields:**

- `event_type`
- `event_id`
- `source`
- `timestamp`
- `payload`

---

## 9. Command Execution Contract

### 9.1 Request

```json
{
  "type": "command_execute",
  "command": "portfolio.sync",
  "payload": {},
  "request_id": "req_002"
}
```

For `toggle` or `selection` commands, the payload SHOULD carry the target value in `value`.

**Examples:**

```json
{
  "type": "command_execute",
  "command": "settings.notifications_enabled.set",
  "payload": {"value": true},
  "request_id": "req_003"
}
```

```json
{
  "type": "command_execute",
  "command": "settings.default_timeframe.set",
  "payload": {"value": "4h"},
  "request_id": "req_004"
}
```

### 9.2 Immediate Ack

IRIS must return the ack quickly, without holding the WebSocket request-response open until the job completes.

```json
{
  "type": "command_ack",
  "request_id": "req_002",
  "operation_id": "op_456",
  "accepted": true
}
```

### 9.3 Final Result

The final outcome is delivered through `operation_update`.

---

## 10. Operation Lifecycle

**Operation statuses:**

- `accepted`
- `queued`
- `in_progress`
- `completed`
- `failed`
- `cancelled`

**Lifecycle example:**

```text
command_execute
  -> command_ack
  -> operation_update: queued
  -> operation_update: in_progress
  -> operation_update: completed
```

---

## 11. Entity Materialization Rules in HA

### 11.1 General Rules

The HA integration must:

- materialize only the entities that arrive in `entities`
- not materialize collections as entities by default
- persist a local registry snapshot
- compare `catalog_version`
- support resync after `catalog_changed`

### 11.2 Behavior When an Entity Disappears

If an entity no longer exists in the catalog:

- do not delete it immediately
- first mark it unavailable or deprecated
- show a migration path when `replacement` exists
- perform physical cleanup only through a separate explicit action

### 11.3 User Overrides

Local HA user settings must not be overwritten by catalog refresh:

- custom name
- area assignment
- disabled-by-user state
- dashboard placement override

Reference v1 strategy:

- the integration keeps entity-level HA overrides untouched through entity-registry updates
- dashboard runtime switches to `local_override` mode if the current Lovelace storage config diverges from the last IRIS-managed render hash
- while `local_override` is active, backend dashboard refreshes keep runtime metadata fresh but do not overwrite the user-edited Lovelace layout

---

## 12. Collections Strategy

Collections are needed for dynamic bulk data such as:

- asset snapshots
- market summary maps
- portfolio snapshots
- prediction journals
- integration status

They must not automatically become hundreds of HA entities.

**Default strategy:**

- collections are stored in the integration’s internal store
- dashboards and cards read them from the store
- entity-per-asset is allowed only as a future promoted mode

---

## 13. Dashboard Contract

### 13.1 Server-Driven Dashboard

IRIS returns only a declarative schema:

- dashboard slug
- views
- sections
- widgets
- data-source bindings

The HA integration is responsible for:

- turning the schema into a Lovelace or panel representation
- preserving local user customizations
- persisting the dashboard instance

### 13.2 Minimal Widget Kinds for v1

- `summary`
- `table`
- `timeline`
- `status`
- `actions`
- `chart_placeholder`
- `list`

---

## 14. Security Model

### 14.1 Required Headers for HTTP Commands

HTTP command surfaces must support:

- `X-IRIS-Actor`
- `X-IRIS-Access-Mode`

Additionally when needed:

- `X-IRIS-Reason`
- `X-IRIS-Control-Token`

### 14.2 WebSocket Auth

For v1, one of the following modes is acceptable:

- token in query or header during upgrade
- pre-authorized local trusted mode
- short-lived session token returned by bootstrap

The final implementation is chosen separately, but the protocol must account for an auth-required path.

---

## 15. Versioning Policy

### 15.1 Protocol Version

`protocol_version` changes only for breaking changes at the transport or message level.

### 15.2 Catalog Version

`catalog_version` is a monotonic opaque string and SHOULD use a content hash or monotonic counter, NOT a date string.

`catalog_version` changes whenever the entity, command, view, or collection catalog changes.

### 15.3 Backend Version

`version` is the ordinary IRIS runtime version.

---

## 16. Error Contract

All transport-level errors must use the same format.

```json
{
  "error": {
    "code": "command_not_available",
    "message": "Command is not available in current mode",
    "details": {
      "command": "portfolio.sync",
      "mode": "ha_addon"
    }
  }
}
```

**Recommended codes:**

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

## 17. Minimal v1 Scope

The first version must include:

### On the IRIS side

- HA bridge consumer on top of the current HA event-bus consumer
- WebSocket gateway
- `/ha/health`
- `/ha/bootstrap`
- `/ha/catalog`
- `/ha/dashboard`
- command-execution adapter
- event-envelope normalization
- `catalog_changed` signaling

### On the HA integration side

- zeroconf discovery
- config flow
- WebSocket session
- entity materializer
- runtime collection store
- command bridge
- basic dashboard creation
- catalog resync

---

## 18. Non-Goals for v1

v1 must not include:

- HA add-on packaging
- complex promoted entity-per-coin mode
- full bidirectional dashboard editor
- offline queueing
- advanced per-user permissions inside HA
- server-driven arbitrary frontend components
- auto-installing the custom integration from IRIS

---

## 19. Open Questions

Still to be fully fixed and documented:

- ~~where the auth boundary lives for WebSocket~~ — **RESOLVED**: v1 uses a bootstrap-issued short-lived session token
- which commands are available only in `full`
- ~~whether a dedicated `/api/v1/ha/state` endpoint is needed for fast reconnect~~ — **RESOLVED**: `/api/v1/ha/state` has been added
- whether `catalog_changed` should include a diff or only a full-refetch instruction

Historical non-protocol implementation questions were captured in the archived [HACS Integration Plan](archive/hacs-integration-plan.md):

- how local dashboard overrides should be stored in HA
- whether the dashboard should render through custom Lovelace cards or a panel

---

## 20. Recommended IRIS-Side Structure

Approximately:

```text
backend/src/apps/integrations/ha/
  api/
  bridge/
  services.py
  query_services.py
  repositories.py
  schemas.py
  websocket.py
  catalog.py
  dashboard.py
  command_bus.py
```

---

## 21. Recommended HA Integration Structure

```text
custom_components/iris/
  __init__.py
  manifest.json
  config_flow.py
  const.py
  client.py
  websocket_client.py
  catalog.py
  entity_factory.py
  store.py
  sensor.py
  binary_sensor.py
  button.py
  switch.py
  select.py
  event.py
  dashboard.py
  services.yaml
```

---

## 22. Final Formulation

The IRIS ↔ HA integration is built as a server-driven, event-driven, bidirectional protocol where:

- IRIS publishes catalog, commands, dashboard schema, and runtime events
- HA materializes only allowed entities and stores collections in its runtime store
- commands execute through the WebSocket command bus
- entity and UI evolution remain declarative, without manual duplication of logic between IRIS and Home Assistant
