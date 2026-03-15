# IRIS HA Custom Integration Backlog

> Historical backlog.
> This checklist is kept as the original rollout backlog and is not the current source of truth.

## Epic / Task Breakdown

---

## Epic 0 — Repo and Delivery Setup

### Goal

Prepare the integration repository and link it to the main IRIS repo through a submodule.

### Tasks

#### 0.1 Create and Prepare `ha-integration-iris`

- create an HACS-compatible custom-integration repository;
- ensure the repository root contains `custom_components/iris/` directly;
- add a basic README;
- add a license if needed;
- define initial version `0.1.0`.

#### 0.2 Convert the Integration to a Git Submodule

- use the correct submodule path under `ha/integration`;
- remove the old tracked directory from the main repo index;
- connect the submodule to `git@github.com:Mesteriis/ha-integration-iris.git`;
- commit `.gitmodules`.

#### 0.3 Update the Main IRIS README

- add an HA integration section;
- document the submodule workflow;
- add clone, init, and update commands;
- describe backend ↔ integration versioned protocol coupling.

#### 0.4 Add Compatibility Metadata

- create `ha/compatibility.yaml`;
- define `protocol_version`;
- define minimum and recommended integration versions;
- define the integration repository source.

#### 0.5 Configure CI Checkout With Submodules

- add recursive checkout;
- verify required submodule files exist;
- add a dedicated integration job.

#### 0.6 Add Pre-Commit and Guard Checks in the Main Repo

- `.gitmodules` validation;
- `ha/compatibility.yaml` validation;
- protocol-drift guard.

### Definition of Done

- [ ] integration repo exists
- [ ] submodule is connected
- [ ] README is updated
- [ ] compatibility metadata is added
- [ ] CI sees the submodule

---

## Epic 1 — HACS Custom Integration Skeleton

### Goal

Create the minimum custom-integration skeleton.

### Tasks

#### 1.1 Create `custom_components/iris`

- `__init__.py`
- `manifest.json`
- `const.py`
- `strings.json`
- `translations/en.json`

#### 1.2 Prepare `manifest.json`

- domain
- name
- config flow
- version
- zeroconf
- documentation
- issue tracker
- codeowners

#### 1.3 Add Basic `config_flow.py`

- `async_step_user`
- `async_step_zeroconf` skeleton
- placeholder validation flow

#### 1.4 Add Basic Entry Setup

- initialize through config entry
- use `ConfigEntry.runtime_data` for typed runtime data
- support `async_unload_entry` and cleanup hooks

#### 1.5 Prepare `diagnostics.py` Skeleton

- basic config-entry diagnostics hook

### Definition of Done

- [ ] integration installs as a custom component
- [ ] HA sees domain `iris`
- [ ] config flow is registered

---

## Epic 2 — Discovery and Bootstrap

### Goal

Enable IRIS discovery and bootstrap connection.

### Tasks

#### 2.1 Implement Zeroconf Discovery

- handle `_iris._tcp.local.`
- parse discovery metadata
- connect it to `async_step_zeroconf`

#### 2.2 Implement Manual Setup

- URL or token input form
- backend validation

#### 2.3 Implement HTTP Bootstrap Client

- `get_health()`
- `get_bootstrap()`
- basic error handling

#### 2.4 Parse Bootstrap Response

- models for instance metadata
- capability flags
- WebSocket, catalog, and dashboard URLs

#### 2.5 Implement Unique Instance Binding

- use `instance_id` as config-entry `unique_id`
- prevent duplicate connection of the same IRIS instance
- update host and port when the same `instance_id` is rediscovered

#### 2.6 Implement HA-Native Flows

- `async_step_reauth`
- `async_step_reconfigure`
- `ConfigEntryAuthFailed`
- `ConfigEntryNotReady`

### Definition of Done

- [ ] manual setup works
- [ ] zeroconf discovery works
- [ ] config entry is created only after successful bootstrap

---

## Epic 3 — Version and Protocol Compatibility

### Goal

Prevent setup against an incompatible backend.

### Tasks

#### 3.1 Create `versioning.py`

- parse integration version
- parse backend version
- parse protocol version

#### 3.2 Implement Compatibility Rules

- compare `protocol_version`
- compare `minimum_ha_integration_version`
- compare `recommended_ha_integration_version`

#### 3.3 Implement User-Facing Errors

- unsupported protocol
- integration too old
- backend too old
- unsupported mode

#### 3.4 Add Compatibility Check to Config Flow

- validate bootstrap before creating the entry

#### 3.5 Add Compatibility Check on Startup

- protect against upgrade drift after the entry already exists

### Definition of Done

- [ ] incompatible versions block setup
- [ ] the user receives a clear error

---

## Epic 4 — WebSocket Session and Live Transport

### Goal

Make WebSocket the primary live transport.

### Tasks

#### 4.1 Implement `websocket_client.py`

- connect
- disconnect
- reconnect
- send message
- receive loop

#### 4.2 Implement Hello/Welcome Handshake

- send `hello`
- handle `welcome`
- validate protocol and capabilities

#### 4.3 Implement Subscribe/Unsubscribe

- subscribe to entities
- subscribe to collections
- subscribe to operations, catalog, and dashboard

#### 4.4 Implement Ping/Pong

- heartbeat handling

#### 4.5 Implement Reconnect Behavior

- reconnect
- repeat handshake
- repeat subscriptions

### Definition of Done

- [ ] integration keeps a stable websocket session
- [ ] reconnect works without manual intervention

---

## Epic 5 — Runtime Store

### Goal

Create an internal store for state, collections, and metadata.

### Tasks

#### 5.1 Implement `store.py`

- current entity state
- collection state
- operation state
- version metadata

#### 5.2 Implement State Access API

- entity state readers
- metadata readers

#### 5.3 Implement Collection Handling

- snapshot writes
- patch application

#### 5.4 Implement Internal Update Signaling

- notify the entity and dashboard layers when store data changes

#### 5.5 Implement Resync and Gap Handling

- track `projection_epoch` and `sequence`
- detect gaps
- trigger full resync on gap or epoch change
- use `/api/v1/ha/state` for authoritative refresh

### Definition of Done

- [ ] store holds live runtime state
- [ ] websocket updates flow into the store correctly

---

## Epic 6 — Catalog Models and Parsing

### Goal

Load the server-driven catalog and validate it safely.

### Tasks

#### 6.1 Create Catalog Models

- entity models
- collection models
- command models
- view models

#### 6.2 Implement `catalog.py`

- fetch and parse catalog
- store `catalog_version`

#### 6.3 Implement `catalog_changed` Handling

- refetch on event
- synchronize materialized state

#### 6.4 Implement Compatibility-Safe Parsing

- tolerate additive fields
- fail clearly on critical schema errors

### Definition of Done

- [ ] integration understands the backend catalog
- [ ] catalog refresh works

---

## Epic 7 — Dynamic Entity Materialization

### Goal

Create HA entities from the backend catalog rather than from a hardcoded list.

### Tasks

#### 7.1 Create `entity_factory.py`

- factory by entity definition

#### 7.2 Create `entity_registry_sync.py`

- compare old and new catalogs
- add new entities
- update metadata
- handle deprecated and hidden status safely

#### 7.3 Implement v1 Platform Support

- sensor
- binary_sensor
- switch
- button
- select
- event

#### 7.4 Implement Entity Base Classes

- read state from the store
- read attributes from the store

#### 7.5 Implement Lifecycle-Aware Behavior

- safe deprecation
- hidden handling
- non-destructive removal flow

#### 7.6 Implement Stable `unique_id`

- `unique_id = f"{instance_id}:{entity_key}"`

#### 7.7 Implement `translation_key` for Entity Names

- use `translation_key`
- set `has_entity_name = True`
- use catalog `name` only as fallback or display hint

### Definition of Done

- [ ] integration materializes entities from the catalog
- [ ] no hardcoded entity list remains in code

---

## Epic 8 — Entity State Updates

### Goal

Let materialized entities live from store data and live updates.

### Tasks

#### 8.1 Handle `entity_state_changed`

- update state and attributes

#### 8.2 Handle `state_patch`

- patch runtime paths
- update dependent entities

#### 8.3 Handle Availability / Connection Degradation

- move entities to unavailable when transport policy requires it

#### 8.4 Implement Compact Attributes Strategy

- avoid copying giant bulk payloads into entity attributes

### Definition of Done

- [ ] HA entities update live from websocket state

---

## Epic 9 — Collections and Bulk Data Strategy

### Goal

Support large dynamic data sets without using a sensor-per-coin model.

### Tasks

#### 9.1 Implement Collection Store

- collection snapshots
- collection metadata

#### 9.2 Handle `collection_snapshot`

- replace collection state safely

#### 9.3 Handle `collection_patch`

- upsert, remove, and update by path

#### 9.4 Expose Collection Access to the Dashboard Layer

- dashboard components read from the store

#### 9.5 Explicitly Exclude Auto-Materialization Per Asset

- no default entity per asset

### Definition of Done

- [ ] bulk state is stored in collections
- [ ] HA is not polluted by per-asset entities

---

## Epic 10 — Command Bridge

### Goal

Support bidirectional control from HA to IRIS.

### Tasks

#### 10.1 Implement `command_bus.py`

- send `command_execute`
- correlate by `request_id`

#### 10.2 Bind Command Availability to the Catalog

- command available only if declared by backend
- availability respects mode and features

#### 10.3 Implement HA Services Mapping

- generic `iris.execute_command`
- optional convenience services only when justified

#### 10.4 Implement UI-Friendly Error Handling

- clear command rejection
- operator-friendly feedback

### Definition of Done

- [ ] commands can be launched from HA
- [ ] the integration does not hardcode commands outside the backend catalog

---

## Epic 11 — Operations Tracking

### Goal

Support lifecycle tracking for long-running commands.

### Tasks

#### 11.1 Implement `operations.py`

- request-to-operation mapping
- current status tracking

#### 11.2 Handle `command_ack`

- store `operation_id`
- link it to the originating request

#### 11.3 Handle `operation_update`

- progress
- completion
- failure
- cancellation

#### 11.4 Implement User Feedback

- clear progress display
- clear completion and failure reporting

### Definition of Done

- [ ] async commands are tracked correctly through operation lifecycle

---

## Epic 12 — Event Relay Into HA

### Goal

Expose IRIS domain events to the HA event layer.

### Tasks

#### 12.1 Handle `event_emitted`

- normalize event types
- map them to HA event surfaces

#### 12.2 Define the Minimal v1 Event Set

- select only useful, stable event categories

#### 12.3 Fix Naming Policy

- clear prefix
- consistent event contract

### Definition of Done

- [ ] the HA automation layer can react to IRIS events

---

## Epic 13 — Dashboard Schema Consumption

### Goal

Create the IRIS dashboard in HA from backend schema.

### Tasks

#### 13.1 Implement `dashboard.py`

- fetch and parse dashboard schema

#### 13.2 Implement Basic Dashboard Creation

- create an `IRIS` dashboard
- create default views

#### 13.3 Bind Widgets to Collections / Store

- widgets consume store-backed data

#### 13.4 Handle `dashboard_changed`

- refetch schema
- update safely

### Definition of Done

- [ ] integration creates a usable IRIS dashboard from backend schema

---

## Epic 14 — Diagnostics and Observability

### Goal

Make the integration debuggable.

### Tasks

#### 14.1 Implement `diagnostics.py`

- connection state
- protocol versions
- catalog state
- last errors

#### 14.2 Implement Internal Debug Logging

- connection lifecycle
- command lifecycle
- resync logic

#### 14.3 Implement Clear Error Surfaces

- avoid “Unknown error” as the default outcome

### Definition of Done

- [ ] diagnostics make failures understandable

---

## Epic 15 — Local Override Safety

### Goal

Avoid breaking local HA settings during catalog refresh.

### Tasks

#### 15.1 Fix Override Safety Rules

- preserve custom names
- preserve area assignment
- preserve user-disabled entities

#### 15.2 Implement Safe Sync Behavior

- update only backend-owned defaults
- respect user-local overrides

### Definition of Done

- [ ] catalog refresh does not destroy local HA customization

---

## Epic 16 — CI, Tests, Quality Gates

### Goal

Stabilize the integration repository.

### Tasks

#### 16.1 Configure Lint / Test Pipeline

- lint
- unit tests
- integration tests

#### 16.2 Add Protocol Contract Tests

- shared canonical fixtures
- backend ↔ integration compatibility checks

#### 16.3 Add Manifest / Repo Sanity Checks

- structure checks
- manifest validation

#### 16.4 Configure Pre-Commit

- formatters
- linters
- guard checks

### Definition of Done

- [ ] the integration repo passes CI
- [ ] contract drift is caught by tests

---

## Epic 17 — Main Repo Integration Guards

### Goal

Stabilize the backend repo ↔ integration submodule link.

### Tasks

#### 17.1 Add Submodule Presence Check in Main-Repo CI

- required files exist
- submodule is initialized correctly

#### 17.2 Add Compatibility Check

- compare versions and protocol metadata

#### 17.3 Add Drift Guard

- CI must fail when backend HA bridge contracts change but compatibility metadata is not updated

#### 17.4 Update Docs Workflow

- how to update submodule ref
- how to update protocol metadata
- how to release compatible versions

### Definition of Done

- [ ] main repo controls compatibility with the integration submodule

---

## Suggested Milestone Breakdown

### Milestone 1 — Foundation

- repo setup
- skeleton
- bootstrap
- compatibility

### Milestone 2 — Live Connectivity

- WebSocket session
- reconnect
- runtime store

### Milestone 3 — Dynamic HA Model

- catalog parsing
- entity materialization
- collections

### Milestone 4 — Bidirectional Control

- command bridge
- operations tracking
- event relay

### Milestone 5 — UX and Hardening

- dashboard
- diagnostics
- CI
- override safety

---

## Most Important First Issues

If the backlog must be cut down to the first actionable issues, the most valuable early items are:

- integration repository + submodule wiring
- bootstrap client + compatibility checks
- WebSocket session lifecycle
- runtime store
- catalog parsing and entity factory
- command bridge
- dashboard bootstrap

## What to Do First in Practice

### Step 1

Finish repository, manifest, and config-flow skeleton.

### Step 2

Implement bootstrap and compatibility checks.

### Step 3

Implement WebSocket session and reconnect.

### Step 4

Implement runtime store and collection handling.

### Step 5

Implement catalog-driven entity materialization.

### Step 6

Add command bridge, operations, dashboard, and hardening.
