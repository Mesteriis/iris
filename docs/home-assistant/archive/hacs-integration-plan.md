# IRIS Home Assistant Custom Integration Plan

> Historical implementation plan.
> The main agreed scope was delivered. The checklist below is retained only as implementation history.

## 1. Component Goal

Build the `iris` custom integration for Home Assistant so that it:

- automatically discovers IRIS through zeroconf;
- connects to IRIS over HTTP and WebSocket;
- fetches bootstrap metadata from IRIS;
- validates protocol and version compatibility;
- loads the entity catalog, command catalog, collections catalog, and dashboard schema;
- dynamically materializes allowed HA entities;
- stores bulk state in an internal runtime store;
- receives live updates over WebSocket;
- sends commands back to IRIS;
- creates the IRIS dashboard in Home Assistant.

## 2. v1 Boundaries

### Included in v1

- HACS-compatible custom component
- zeroconf discovery
- config flow
- HTTP bootstrap client
- WebSocket session
- runtime store
- dynamic catalog-driven entity materialization
- command bridge
- operation tracking
- dashboard-schema consumption
- compatibility and version checks
- submodule integration in the main repo
- CI, pre-commit, and compatibility guards

### Not Included in v1

- add-on packaging
- auto-installation from the backend
- entity-per-asset promoted mode
- visual dashboard editor
- complex offline sync
- multi-user permission model
- arbitrary frontend component engine

## 3. Repository Model

### Separate Integration Repository

Component repository:

```text
git@github.com:Mesteriis/ha-integration-iris.git
```

### Connected to the Main IRIS Repo

Submodule path:

```text
ha/integration
```

### Required in the Main Repo

- `.gitmodules`
- a README section about the HA integration
- `ha/compatibility.yaml`
- CI checkout with submodules
- pre-commit checks for compatibility and protocol drift

## 4. Custom Component Structure

Recommended structure:

```text
custom_components/iris/
  __init__.py
  manifest.json
  const.py
  config_flow.py
  diagnostics.py

  client.py
  websocket_client.py
  bootstrap.py
  versioning.py

  catalog.py
  entity_factory.py
  entity_registry_sync.py

  store.py
  subscriptions.py
  command_bus.py
  operations.py

  sensor.py
  binary_sensor.py
  button.py
  switch.py
  select.py
  event.py

  dashboard.py
  services.yaml
  strings.json
  translations/
    en.json

  models/
    __init__.py
    bootstrap.py
    catalog.py
    commands.py
    dashboard.py
    websocket.py
    state.py
```

## 5. `manifest.json`

### Must Include

- `domain`
- `name`
- `config_flow`
- `version`
- `zeroconf`
- `documentation`
- `issue_tracker`
- `codeowners`
- dependencies only if genuinely needed

### Zeroconf

IRIS discovery must use:

```text
_iris._tcp.local.
```

### Manifest Example

```json
{
  "domain": "iris",
  "name": "IRIS",
  "config_flow": true,
  "version": "0.1.0",
  "zeroconf": ["_iris._tcp.local."],
  "documentation": "https://github.com/Mesteriis/ha-integration-iris",
  "issue_tracker": "https://github.com/Mesteriis/ha-integration-iris/issues",
  "codeowners": ["@Mesteriis"]
}
```

## 6. Discovery and Pairing

### 6.1 Zeroconf Discovery

The integration must support:

- `async_step_zeroconf`
- `async_step_user`

### 6.2 Connection Flow

#### Through Zeroconf

1. HA detects `_iris._tcp.local.`
2. It starts `async_step_zeroconf`
3. The integration receives:
   - host
   - port
   - `instance_id`
   - version
   - `protocol_version`
4. It calls bootstrap
5. It validates compatibility
6. It creates the config entry

#### Through Manual Setup

1. The user enters URL or token
2. The integration calls bootstrap
3. It validates the backend
4. It creates the config entry

## 7. Bootstrap Contract

Use backend endpoint:

```text
/api/v1/ha/bootstrap
```

Read from bootstrap:

- `instance_id`
- `display_name`
- `version`
- `protocol_version`
- `catalog_version`
- `mode`
- `minimum_ha_integration_version`
- `recommended_ha_integration_version`
- `catalog_url`
- `dashboard_url`
- `ws_url`

## 8. Compatibility Checks

### Required Logic

The integration must validate during config flow and startup:

- `protocol_version`
- minimum integration version
- recommended integration version
- backend mode support

### Incompatibility Behavior

On incompatibility, setup must stop with a clear user-facing error.

### Separate Module

Keep compatibility logic in `versioning.py` or a dedicated compatibility module rather than scattering it across flow code.

## 9. HTTP Client

### What It Must Support

- `get_health()`
- `get_bootstrap()`
- `get_catalog()`
- `get_dashboard()`
- optional `get_state()`
- typed error handling

### What Not to Add

- duplicated business logic from the backend
- ad-hoc command semantics
- independent catalog truth

## 10. WebSocket Client

### Responsibilities

- connect
- disconnect
- reconnect
- send typed messages
- run a receive loop
- handle `hello` / `welcome`
- manage subscriptions
- trigger resync on gaps or epoch changes

### Supported Incoming Messages

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

### Supported Outgoing Messages

- `hello`
- `subscribe`
- `unsubscribe`
- `command_execute`
- `ping`
- optional `ack_event`

## 11. Runtime Store

### Store Goal

The runtime store exists to:

- keep the latest entity state;
- store collection data;
- cache operation status;
- keep protocol metadata such as epoch and sequence;
- act as the data source for entities and dashboard rendering.

### Why the Store Matters

Without the store, entity logic, WebSocket handling, and dashboard rendering become tightly coupled and harder to reason about.

### What to Store as Collections

- asset snapshots
- portfolio snapshots
- prediction snapshots
- system or integration summary collections

## 12. Catalog-Driven Materialization

### Core Rule

The integration does not know the entity list in advance.
It materializes what arrives from the backend catalog.

### Needed Modules

- `catalog.py`
- `entity_factory.py`
- `entity_registry_sync.py`

### Their Responsibilities

- load and validate the catalog;
- store the parsed catalog model;
- create entity classes from catalog records;
- compare old and new catalog versions;
- add new entities;
- update metadata;
- handle deprecation safely.

## 13. Supported Platforms in v1

Support:

- sensor
- binary_sensor
- switch
- button
- select
- event

`number` may be supported only if it is actually present in the backend catalog and fits the v1 compatibility contract.

### Important

Do not build `sensor-per-coin` as the default model.

## 14. Entity Strategy

### Entities That Truly Matter in v1

Prefer stable, compact, automation-friendly entities:

- system state
- integration state
- selected portfolio controls
- selected settings controls
- limited diagnostic and action entities

## 15. Command Bridge

### Tasks

- read command definitions from the catalog
- send `command_execute`
- correlate by `request_id`
- keep `operation_id`
- track lifecycle through `operation_update`

### Minimum Commands to Support

- asset management
- source connectivity actions
- settings toggles or selections
- portfolio sync and refresh actions

## 16. Operations Tracking

### What to Store

- `request_id`
- `operation_id`
- command key
- current status
- last message
- timestamps

### Behavior

- immediate ack arrives quickly
- execution is tracked through WebSocket
- errors are displayed in a UI-friendly way

## 17. Dashboard Layer

### Approach

The dashboard must be built from server-driven schema, not from hardcoded HA layout.

### In v1

It is enough to:

1. create a dedicated IRIS dashboard;
2. load the dashboard schema;
3. create basic views and widgets;
4. bind widgets to collections and state.

### Important

Do not try to build a full smart UI builder in the first phase.

## 18. Services in HA

`services.yaml` should describe user-facing actions.

The source of truth still remains the backend catalog. `services.yaml` exists for HA UX integration, not for duplicating business logic.

## 19. Diagnostics

### What to Show

- backend connectivity
- protocol and catalog versions
- auth state
- session health
- last error
- resync state
- selected runtime metadata

## 20. User-Local Overrides

### Never Overwrite

- custom names
- area assignments
- user-disabled entities
- later local dashboard rearrangements

The backend may update only backend-owned defaults.

## 21. Reconnect Behavior

The WebSocket connection must be robust.

On reconnect:

- repeat `hello`
- repeat subscriptions
- refresh state when needed
- refetch catalog if `catalog_changed` or version drift is detected

## 22. Errors and UX

Human-readable errors are required for:

- auth failures
- incompatibility
- bootstrap failure
- command rejection
- reconnect failure
- resync-required cases

## 23. Testing

### Unit Tests

Cover:

- version parsing
- bootstrap parsing
- catalog parsing
- store behavior
- entity factory logic
- WebSocket message handling

### Integration Tests

Cover:

- config flow
- zeroconf
- bootstrap + compatibility path
- reconnect behavior
- command lifecycle

### Contract Tests

Verify:

- protocol compatibility with backend fixtures
- catalog shape
- message handling compatibility

## 24. CI for the Integration Repo

Need jobs for:

- lint
- unit tests
- integration tests
- protocol contract checks
- manifest and repo sanity checks

## 25. Pre-Commit for the Integration Repo

Add:

- formatting
- linting
- manifest checks
- guard against breaking required repository structure

## 26. Relation to the Main IRIS Repo

### When Backend Changes the Protocol

The main repo must:

- update protocol docs;
- update compatibility metadata;
- update the integration repo if needed;
- update the submodule reference.

### In the Main Repo

Add guards so that when backend HA bridge contracts change but `ha/compatibility.yaml` is not updated, CI fails.

## 27. Compatibility File

The main repo should carry compatibility metadata describing:

- protocol version
- minimum supported integration version
- recommended integration version
- integration source reference

The runtime integration should validate bootstrap against this compatibility model.

## 28. Implementation Stages

### Stage 1 — Skeleton

- repository and component skeleton
- manifest
- config flow

### Stage 2 — Bootstrap + Compatibility

- bootstrap client
- compatibility checks
- config-entry creation

### Stage 3 — Runtime Session

- WebSocket lifecycle
- subscribe and reconnect

### Stage 4 — Catalog-Driven Entity Model

- catalog parsing
- entity factory
- registry sync

### Stage 5 — Store + Collections

- runtime store
- collection handling
- resync logic

### Stage 6 — Commands + Operations

- command bus
- command ack
- operation lifecycle

### Stage 7 — Dashboard

- dashboard schema
- initial Lovelace generation

### Stage 8 — Hardening

- diagnostics
- CI
- pre-commit
- drift guards

## 29. Definition of Done

The integration is considered ready for v1 when it:

- installs as a custom integration;
- supports manual setup and zeroconf discovery;
- validates compatibility before setup;
- keeps a stable WebSocket session;
- materializes entities from the catalog;
- stores bulk state in collections;
- sends commands back to IRIS;
- tracks operations correctly;
- creates a usable IRIS dashboard;
- respects local HA overrides;
- passes CI and protocol contract checks.

## 30. Critical Pitfalls

Do not:

- mix the integration with backend domain logic;
- turn collections into hundreds of default entities;
- hardcode catalog truth in two places;
- let reconnect behavior degrade into manual recovery;
- lose compatibility metadata discipline between repos.

## 31. Recommended First Sprints

### Sprint 1

- repo skeleton
- manifest
- config flow
- bootstrap client
- compatibility checks

### Sprint 2

- WebSocket session
- runtime store
- catalog parsing
- entity materialization

### Sprint 3

- command bridge
- operation tracking
- dashboard generation
- diagnostics and CI hardening
