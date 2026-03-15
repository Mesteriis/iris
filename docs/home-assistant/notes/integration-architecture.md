# Home Assistant Integration Architecture Note

> **Status: Informational note**
>
> This document is not an ADR and does not define normative rules. See the detailed specifications in:
> - [Protocol Specification](../protocol-specification.md) — authoritative protocol contract
> - [Home Assistant Archive](../archive/index.md) — historical implementation plans and rollout material
>
> If this document conflicts with the spec, **the spec is the source of truth**.

## Goal

Enable bidirectional integration between IRIS and Home Assistant where:

- IRIS remains the source of truth for entities, commands, and UI models.
- Home Assistant acts as the UI host, automation engine, and notification layer.
- synchronization is event-driven through the event bus and a server-driven catalog, without polling as the main model.
- the integration supports dynamic entities and IRIS extensibility without requiring HA-component rewrites.

---

## High-Level Architecture

The system consists of two components.

```text
┌─────────────────────────────────────────────────────────────────┐
│                           IRIS Backend                          │
│  ┌───────────────┐                                              │
│  │   Event Bus   │  (Redis Streams)                             │
│  │    (Redis)    │                                              │
│  └───────┬───────┘                                              │
│          │                                                      │
│  ┌───────▼────────┐                                             │
│  │  HA Event      │                                             │
│  │  Consumer      │ -> WebSocket / Event Gateway                │
│  └────────────────┘                                             │
│                                                                 │
│  ┌───────────────────────────────────────┐                      │
│  │     HA Entity Catalog API             │                      │
│  └───────────────────────────────────────┘                      │
│  ┌───────────────────────────────────────┐                      │
│  │     HA Command API                    │                      │
│  └───────────────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Home Assistant                             │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │     Custom Integration: iris                              │  │
│  │                                                           │  │
│  │   ┌─────────────┐   ┌─────────────────┐   ┌───────────┐  │  │
│  │   │  WebSocket  │   │      Entity     │   │  Command  │  │  │
│  │   │   client    │   │   materializer  │   │   bridge  │  │  │
│  │   └─────────────┘   └─────────────────┘   └───────────┘  │  │
│  │                                                           │  │
│  │   ┌─────────────────┐   ┌──────────────────────────────┐  │  │
│  │   │ Runtime state   │   │     Dashboard renderer       │  │  │
│  │   │     store       │   │                              │  │  │
│  │   └─────────────────┘   └──────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component 1: IRIS HA Bridge (Backend)

### Purpose

The IRIS HA Bridge is responsible for:

- translating events from the IRIS event bus to Home Assistant;
- exposing the entity catalog;
- handling commands from HA;
- publishing runtime state.

This component is embedded in the IRIS backend.

### 1.1 Event-Bus Consumer

The system already contains a Home Assistant consumer in the event bus.

**Current behavior:**

```text
event -> print()
```

It must be extended into an HA Bridge Service.

#### New Functionality

The consumer must:

1. listen to Redis Streams events on `iris_events`;
2. filter the events intended for HA;
3. publish them through the WebSocket gateway.

#### Event Types

IRIS must translate:

- `decision_generated`
- `final_signal_generated`
- `market_regime_changed`
- `prediction_confirmed`
- `prediction_failed`
- `portfolio_action`
- `portfolio_state_changed`
- `pattern_state_changed`
- `operation_started`
- `operation_progress`
- `operation_completed`
- `operation_failed`

Implementation note:

- abstract event families may materialize as concrete runtime event names;
- the current HA bridge already supports concrete portfolio variants such as `portfolio_balance_updated`, `portfolio_position_*`, and `portfolio_rebalanced`;
- `pattern_state_changed` is currently represented by concrete variants such as `pattern_boosted`, `pattern_degraded`, and `pattern_disabled`.

Each event must use a standard envelope.

#### Event Envelope

```json
{
  "event_type": "decision_generated",
  "timestamp": "...",
  "source": "decision_engine",
  "payload": {}
}
```

### 1.2 WebSocket Gateway

The HA integration connects to IRIS through WebSocket.

**Reasons:**

- bidirectional communication;
- push updates;
- command execution;
- operation tracking.

**Endpoint:** `/api/v1/ha/ws`

#### Supported Messages

**Server -> HA**

- `state_patch`
- `entity_state_changed`
- `collection_patch`
- `catalog_changed`
- `dashboard_changed`
- `operation_update`
- `system_health`

**HA -> Server**

- `command_execute`
- `subscribe`
- `unsubscribe`
- `ack_event`
- `ping`

---

## Component 2: Home Assistant Custom Integration

`custom_components/iris`

This component is a thin adapter between IRIS and Home Assistant.

### 2.1 Primary Responsibilities

The integration must:

1. discover IRIS through mDNS / zeroconf;
2. establish a WebSocket connection;
3. fetch the entity catalog;
4. materialize HA entities;
5. maintain a runtime state store;
6. receive events and update entities;
7. send commands to IRIS;
8. create the dashboard.

### 2.2 Discovery

IRIS must publish zeroconf:

```text
_iris._tcp.local
```

**TXT records:**

- `instance_id`
- `version`
- `api_port`
- `ws_path`
- `mode`

HA integration:

```yaml
# manifest.json
zeroconf:
  - "_iris._tcp.local."
```

### 2.3 Connection Flow

After discovery:

1. HA opens config flow;
2. the user confirms the connection;
3. the integration receives `instance_id`;
4. WebSocket opens;
5. the integration fetches the catalog.

---

## Entity Catalog

IRIS must be the single source of truth for entities.

Home Assistant must not contain hardcoded entities.

**Endpoint:** `/api/v1/ha/catalog`

**Response:**

```json
{
  "catalog_version": "2026.03",
  "mode": "full",
  "entities": [],
  "collections": [],
  "commands": [],
  "views": []
}
```

### Entity Definition

Each entity is declared declaratively.

```json
{
  "entity_key": "system.connection",
  "platform": "binary_sensor",
  "name": "IRIS Connection",
  "icon": "mdi:lan-connect",
  "category": "diagnostic",
  "default_enabled": true,
  "state_source": "system.connection",
  "device_class": "connectivity"
}
```

### Supported Platforms

- `sensor`
- `binary_sensor`
- `switch`
- `button`
- `select`
- `number`
- `event`

### Materialization Logic

On startup, the integration:

1. fetches the catalog;
2. compares it with the local registry;
3. creates new entities;
4. updates metadata;
5. disables deprecated entities.

---

## Collection Model

Collections are used for larger data sets instead of entities.

**Example:**

```json
{
  "collection_key": "assets.snapshot",
  "kind": "mapping",
  "transport": "websocket",
  "dashboard_only": true
}
```

**Snapshot example:**

```json
{
  "assets": {
    "BTC": {
      "decision": "BUY",
      "confidence": 0.81,
      "risk": 0.63
    }
  }
}
```

---

## Command Catalog

IRIS declares commands.

**Example:**

```json
{
  "command_key": "asset.add",
  "input_schema": {
    "symbol": "string"
  },
  "returns": "operation"
}
```

### Supported Commands

- `asset.add`
- `asset.remove`
- `asset.watch_enable`
- `news.connect_source`
- `news.disconnect_source`
- `telegram.start_auth`
- `telegram.confirm_auth`
- `portfolio.sync`
- `market.refresh`

### Command Execution

HA sends:

```json
{
  "type": "command_execute",
  "command": "asset.add",
  "payload": {
    "symbol": "BTC"
  }
}
```

IRIS returns an `operation_id`.

### Operation Tracking

HA receives:

- `operation_started`
- `operation_progress`
- `operation_completed`
- `operation_failed`

---

## Dashboard

IRIS must expose dashboard schema.

**Endpoint:** `/api/v1/ha/dashboard`

**Response:**

```json
{
  "version": 1,
  "views": []
}
```

### Dashboard Creation

The integration must:

1. create a Lovelace dashboard called `IRIS`;
2. create views:
   - `Overview`
   - `Assets`
   - `Signals`
   - `Portfolio`
   - `Predictions`
   - `Integrations`
   - `System`

---

## Entity Strategy

To avoid thousands of entities:

- **default**: aggregate sensors;
- **optional**: the user may promote an asset into an entity.

### Lifecycle

Entities may have the following status:

- `active`
- `deprecated`
- `hidden`
- `removed`

### Compatibility

Each entity must carry:

- `since_version`
- `deprecated_since`
- `replacement`

---

## Security

All commands require:

- `X-IRIS-Actor`
- `X-IRIS-Access-Mode`

---

## Implementation Roadmap

### Phase 1

**IRIS:**

- HA bridge service
- event consumer
- WebSocket gateway

**HA:**

- basic custom integration
- WebSocket client
- entity materializer

### Phase 2

- entity catalog
- command catalog
- runtime collections

### Phase 3

- dashboard schema
- automatic dashboard creation

### Phase 4

- advanced entity lifecycle
- user overrides
- promoted entities

### Phase 5

- Home Assistant add-on
- Supervisor integration
- full packaging

---

## Summary

The system should implement a server-driven Home Assistant integration where:

- IRIS is the source of truth;
- HA is the UI and automation layer;
- all entities, commands, and dashboard definitions are declared through a catalog;
- synchronization runs through the event bus and WebSocket.

## See also

- [Home Assistant Notes](index.md)
- [Protocol Specification](../protocol-specification.md)
- [Home Assistant Archive](../archive/index.md)
