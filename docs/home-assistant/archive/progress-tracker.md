# Home Assistant Progress Tracker

> Status: Historical tracker
>
> Last updated: 2026-03-15
>
> This document is archived rollout tracking only.
> Normative source of truth remains:
> - [Protocol Specification](../protocol-specification.md)
> - [Integration Architecture Note](../notes/integration-architecture.md)
> - [Backend Implementation Plan](backend-implementation-plan.md)
> - [HACS Integration Plan](hacs-integration-plan.md)
> - [Task Backlog](task-backlog.md)

---

## Progress Legend

- `Done` = stage is functionally complete for the current agreed scope
- `In progress` = work started but exit criteria not met
- `Planned` = not started yet
- Progress bars are approximate and updated manually

---

## Overall Status

- Overall progress: `[##########] 100%`
- Current stage: `Completed`
- Next stage: `Optional follow-up only`
- Current reality: backend protocol surface, live bridge, projector and command slice now exist end-to-end; the HA custom component has bootstrap/runtime/websocket foundations plus discovery/auth flows, validated catalog parsing, catalog-backed platform coverage for `sensor`/`binary_sensor`/`switch`/`button`/`select`/`event`, in-place catalog add/update/remove sync, generic `execute_command` services, websocket command ack matching, real backend `portfolio.sync` / `market.refresh` dispatch, backend-backed `switch/select` write semantics, live `operation_update`, shared backend/integration contract fixtures, and a managed storage-Lovelace dashboard rendered from backend schema with `Overview` / `Assets` / `Signals` / `Predictions` / `Portfolio` / `Integrations` / `System` views plus local override protection

---

## Stage Board

| Stage | Status | Progress | Result |
|------|--------|----------|--------|
| Stage 0 - Protocol and planning | Done | `[##########] 100%` | ADR/spec/plans/tasks fixed and aligned |
| Stage 1 - Backend transport foundation | Done | `[##########] 100%` | HTTP + WS protocol surface exists in IRIS backend |
| Stage 2 - Backend live bridge and projector | Done | `[##########] 100%` | Redis Streams consumer, projector, live relay, server-side resync fallback, live `operation_update`, and projector coverage for the current HA-facing runtime event families are implemented |
| Stage 3 - HA integration bootstrap/runtime store | Done | `[##########] 100%` | custom component now uses bootstrap, typed runtime_data, runtime store, websocket reconnect/runtime tests, discovery/auth flows, generic command bus wiring and real HA tests |
| Stage 4 - Dynamic HA model and control loop | Done | `[##########] 100%` | validated backend catalog now drives `sensor`/`binary_sensor`/`switch`/`button`/`select`/`event`, `catalog_changed` applies in-place add/update/remove sync, `dashboard_changed` refreshes runtime/dashboard state, and the first real control commands run end-to-end |
| Stage 5 - Dashboard, delivery and hardening | Done | `[##########] 100%` | managed Lovelace dashboard rendering, live collection-aware cards, local override protection, shared contract fixtures, pinned submodule metadata and release/update workflow are in place |

---

## Stage 0 - Protocol and planning

- Status: `Done`
- Progress: `[##########] 100%`

### Done

- HA protocol spec prepared and made authoritative
- ADR and implementation plans added
- task backlog split into milestones and epics
- backend and integration responsibilities separated clearly

### Remaining

- keep documents in sync as implementation changes the real surface

---

## Stage 1 - Backend transport foundation

- Status: `Done`
- Progress: `[##########] 100%`

### Done

- added new HA backend module under `backend/src/apps/integrations/ha/`
- added protocol-facing HTTP endpoints:
  - `/api/v1/ha/health`
  - `/api/v1/ha/bootstrap`
  - `/api/v1/ha/catalog`
  - `/api/v1/ha/dashboard`
  - `/api/v1/ha/state`
  - `/api/v1/ha/operations/{operation_id}`
- added base websocket endpoint:
  - `/api/v1/ha/ws`
- implemented websocket lifecycle for:
  - `hello`
  - `welcome`
  - `subscribe`
  - `unsubscribe`
  - `ping`
  - negative `command_ack` for unsupported commands
- added initial server-driven catalog for:
  - entities
  - collections
  - dashboard views
- added initial runtime snapshot sourced from current backend state:
  - system connection/mode
  - market asset summary
  - portfolio summary
  - notifications enabled flag
- added projection epoch/sequence foundation for state-bearing websocket messages
- registered HA router in API v1
- added HA settings/version metadata to backend settings
- added backend tests for HTTP contracts and websocket handshake/snapshot flow

### Files added/changed

- `backend/src/apps/integrations/ha/`
- `backend/src/api/v1/router.py`
- `backend/src/apps/__init__.py`
- `backend/src/core/settings/base.py`
- `backend/tests/apps/integrations/test_ha_views.py`

### Verified

- `ruff` passes for the new backend HA module
- dedicated HA backend tests pass

### Remaining

- this stage intentionally does **not** include live Redis event relay
- this stage intentionally does **not** include real command dispatch
- websocket currently provides initial sync and basic session semantics, not full live bridge behavior

---

## Stage 2 - Backend live bridge and projector

- Status: `Done`
- Progress: `[##########] 100%`

### Goal

Turn the current HA transport surface into a real event-driven bridge.

### Done

- added HA bridge runtime bound to app lifespan
- added Redis Streams consumer for HA bridge over `iris_events`
- added dedicated HA consumer group bootstrap to avoid replaying old backlog on first start
- added runtime projector fed by supported IRIS events
- added live websocket relay through the HA hub/session queue model
- added server-side `resync_required` fallback for outbound session queue overflow
- implemented live messages for the current supported slice:
  - `event_emitted`
  - `state_patch`
  - `collection_patch`
  - `resync_required`
- implemented live projection for the first event families:
  - market asset updates
  - prediction updates
  - portfolio summary/positions refresh
- fixed websocket subscribe flow so initial sync is sent before live relay is enabled for the session
- added targeted test coverage for `event -> projector -> websocket relay`

### Supported live event slice

- `decision_generated`
- `market_regime_changed`
- `prediction_confirmed`
- `prediction_failed`
- `portfolio_balance_updated`
- `portfolio_position_changed`
- `portfolio_position_opened`
- `portfolio_position_closed`
- `portfolio_rebalanced`

### Remaining

- add `catalog_changed` / `dashboard_changed` live notifications when those surfaces become mutable at runtime
- harden and verify end-to-end reconnect/resync behavior against integration-side protocol tests
- broaden projector coverage for the rest of backend event taxonomy as new entities/collections are added
- decide whether projector snapshots must persist across process restarts or can remain rebuildable in-memory

### Exit criteria

- HA client can stay connected and receive live state changes without polling
- reconnect/resync path is deterministic

---

## Stage 3 - HA integration bootstrap/runtime store

- Status: `Done`
- Progress: `[##########] 100%`

### Goal

Replace the current legacy polling custom component behavior with protocol-driven bootstrap + websocket runtime.

### Done

- removed the old polling coordinator from the active setup path
- added HTTP bootstrap/catalog/dashboard/state client in `ha/integration/custom_components/iris/client.py`
- added bootstrap parsing and compatibility rules in:
  - `ha/integration/custom_components/iris/bootstrap.py`
  - `ha/integration/custom_components/iris/versioning.py`
- moved integration runtime to typed `ConfigEntry.runtime_data`
- added in-memory runtime store for:
  - bootstrap metadata
  - catalog
  - dashboard
  - entity state
  - collections
  - operations
  - connection / projection metadata
- added websocket runtime client with:
  - hello / welcome
  - subscribe
  - reconnect loop
  - `/api/v1/ha/state` refresh on reconnect and resync
  - `resync_required` handling
  - sequence / epoch gap detection
  - outbound `command_execute`
  - inbound `command_ack` request matching
- added isolated HA integration `uv` project with pinned Home Assistant test dependencies
- added explicit `zeroconf` dependency to the isolated HA test env so discovery flows can be executed and tested locally
- added `async_step_zeroconf` with host/port update semantics on repeated discovery of the same `instance_id`
- added `async_step_reauth` with token refresh and config entry reload/update path
- added `async_step_reconfigure` for backend URL changes and verified native flow-manager entry on the `2026.3.1` Home Assistant baseline
- fixed websocket runtime so backend-triggered refresh/resync messages cause immediate reconnect without waiting for backoff
- added websocket handling for `catalog_changed` / `dashboard_changed` refresh paths with catalog reload callback support
- added initial integration-side tests for:
  - config flow bootstrap validation
  - zeroconf discovery + duplicate update behavior
  - reauth token refresh
  - direct and native flow-manager `reconfigure` behavior
  - websocket hello / welcome / subscribe handshake
  - domain event relay from `event_emitted`
  - `resync_required` state refresh behavior
  - immediate reconnect after backend-triggered resync
  - `catalog_changed` catalog refetch + reload callback path
  - `dashboard_changed` dashboard refetch path
  - config entry setup/runtime_data population
  - runtime store resync/gap semantics
- updated manifest to `local_push` and added zeroconf/docs metadata
- added diagnostics hook and config-flow strings
- rewired the current sensor platform to the runtime store instead of polling
- added generic HA service registration:
  - `iris.execute_command`
  - `iris.sync_portfolio`
  - `iris.refresh_market`
- added command bus wiring between HA services / catalog-backed controls and the websocket transport
- added tests for websocket command ack handling and service-level command dispatch

### Remaining

- keep the isolated HA env pinned and regularly verified against the selected `2026.3.1` baseline
- decide whether dashboard should be refreshed eagerly on reconnect or only on `dashboard_changed`

### Exit criteria

- integration can connect to backend using bootstrap + websocket only
- no polling is required for primary live state

---

## Stage 4 - Dynamic HA model and control loop

- Status: `Done`
- Progress: `[##########] 100%`

### Goal

Make Home Assistant materialize and control IRIS from backend-owned catalogs.

### Done

- sensor platform now materializes backend-owned `platform == "sensor"` entities from the runtime catalog
- binary_sensor platform now materializes backend-owned `platform == "binary_sensor"` entities from the runtime catalog
- removed the legacy hardcoded `sensor.connection` fallback from the active entity path
- added a shared entity helper layer for current catalog-backed platforms
- catalog-driven sensors use stable unique IDs in the form `instance_id:entity_key`
- current backend-published entity set is now materialized dynamically through supported platforms
- added explicit client-side catalog parser/validator for backend payloads before they enter the runtime store
- `catalog_changed` now refetches catalog and applies fine-grained in-place sync for add/update paths
- catalog lifecycle metadata now affects HA materialization:
  - `availability.status == "hidden"` hides entities through the registry
  - `availability.status == "deprecated"` defaults new entities to integration-disabled state
  - `entity_registry_enabled_default` / `default_enabled` affect initial enabled state
  - `availability.modes` filters entities against the current backend mode
  - `availability.status == "removed"` falls back to config entry reload instead of silent drift
- integration-side catalog platform coverage now matches the ADR/plans scope:
  - `sensor`
  - `binary_sensor`
  - `switch`
  - `button`
  - `select`
  - `event`
- control-oriented catalog platforms are materialized honestly before command bridge readiness:
  - `switch`, `button`, `select` expose backend-owned state/metadata
  - `button` actions now execute through the real command bridge when `command_key` is present
  - `switch` and `select` now execute backend-owned `toggle` / `selection` commands through the same command bus
  - `event` entities can project store-driven last event payloads into HA event entity state
- catalog refresh behavior is now tested against ADR-style local override requirements:
  - custom name remains untouched
  - user-disabled state remains untouched
- dashboard schema now has an HA-side runtime consumer:
  - initial dashboard load publishes normalized runtime summary
  - `dashboard_changed` refresh publishes `iris.dashboard_updated`
  - dashboard summary/hash is available for diagnostics and future UI consumers
- backend catalog now publishes the first control-capable surface:
  - `commands`: `portfolio.sync`, `market.refresh`, `settings.notifications_enabled.set`, `settings.default_timeframe.set`
  - control-bound `button` / `switch` / `select` entities with explicit `command_key`
- websocket command execution now works end-to-end:
  - backend returns positive `command_ack`
  - backend tracks queued/running/terminal operation state
  - HA runtime store receives live `operation_update`
  - HA services and catalog-backed controls can trigger backend commands
- removed catalog entities now retire in place:
  - no config entry reload is required for `availability.status == "removed"`
  - loaded entities are removed from the entity platform
  - stale entity-registry entries are dropped as part of catalog sync
- added HA test coverage for parser validation, sensor/binary_sensor materialization, runtime-backed state values, lifecycle defaults, mode filtering and catalog refresh add/update/remove behavior

### To do

- turn dashboard runtime schema into Lovelace/panel representation
- widen backend command catalog beyond the first two operations and bind richer control entities to it
- decide whether Stage 4 should be closed before dashboard rendering begins, or whether that work belongs fully to Stage 5

### Exit criteria

- no hardcoded backend-owned entity list remains in integration
- commands and operations flow end-to-end

---

## Stage 5 - Dashboard, delivery and hardening

- Status: `Done`
- Progress: `[##########] 100%`

### Goal

Finish the HA experience and stabilize delivery workflow.

### Done in this stage

- client-side dashboard payloads are now parsed and validated before entering the runtime store
- backend dashboard schema now advertises the planned ADR-facing views:
  - `Overview`
  - `Assets`
  - `Signals`
  - `Predictions`
  - `Portfolio`
  - `Integrations`
  - `System`
- HA integration now creates a managed storage-Lovelace dashboard from backend schema instead of only keeping runtime summary metadata
- `dashboard_changed` now refetches schema and updates the managed Lovelace dashboard in place
- summary/status widgets resolve real HA entities through the entity registry
- actions widgets render to real HA buttons or `iris.execute_command` service calls
- collection-backed widgets now render as live collection-aware built-in Lovelace cards backed by the runtime store instead of a single snapshot markdown blob
- dashboard runtime now refreshes the managed Lovelace config on store-driven collection changes, not only on `dashboard_changed`
- dashboard runtime now preserves local Lovelace edits through `local_override` mode instead of overwriting user-managed layout changes
- diagnostics/runtime summary now include Lovelace sync metadata such as dashboard URL path and render hash
- isolated integration repo metadata now exists:
  - `ha/integration/README.md`
  - `ha/integration/hacs.json`
  - `ha/integration/LICENSE`
  - `ha/integration/.github/workflows/ci.yml`
- integration repo has been initialized and pushed to `git@github.com:Mesteriis/ha-integration-iris.git`
- main repo now has:
  - `ha/compatibility.yaml`
  - a README section describing the backend ↔ integration contract
  - `.gitmodules` plus a real gitlink/submodule entry for `ha/integration`
- `ha/compatibility.yaml` now pins the expected `ha/integration` commit SHA in addition to protocol/version metadata
- main repo now validates the integration contract through:
  - `scripts/check_ha_integration_contract.py`
  - `.github/workflows/ha-integration-governance.yml`
- shared backend/integration contract fixtures now live in `ha/integration/tests/fixtures/contract/` and are exercised from both repos
- main repo now has an automation path for submodule bump PRs:
  - `scripts/update_ha_integration_submodule.py`
  - `.github/workflows/update-ha-integration-submodule.yml`
- the guard is now diff-aware for PR/push ranges:
  - if backend HA bridge contract files change
  - CI now requires a companion change in protocol spec, compatibility metadata or the integration submodule ref

### Exit criteria

- integration delivery is reproducible
- protocol drift is caught automatically

---

## What Is Done Right Now

- backend protocol surface exists and is test-covered
- server-driven bootstrap/catalog/dashboard/state snapshots exist
- websocket session contract is in place
- live Redis Streams -> HA bridge exists for the initial supported event slice
- runtime projection is updated incrementally and broadcast to websocket subscribers
- backend can now force client resync on detected session queue overflow instead of silently dropping state-bearing messages
- HA custom component now boots through backend bootstrap, stores runtime in `ConfigEntry.runtime_data`, and maintains a reconnecting websocket runtime store
- HA integration now has its own isolated Home Assistant test environment with `zeroconf` support and passing protocol/config-flow tests
- HA websocket runtime now has direct tests for handshake, `event_emitted`, `resync_required` refresh and immediate reconnect semantics
- HA websocket runtime now refreshes catalog/dashboard on control messages and can do in-place add/update sync for materialized entities
- catalog-backed platform coverage now exists for `sensor`, `binary_sensor`, `switch`, `button`, `select` and `event`
- catalog lifecycle metadata now drives hidden/default-enabled behavior for current catalog-backed entities
- catalog payloads are validated on the client side before entering the runtime store, which aligns the integration with the protocol contract instead of trusting raw JSON
- dashboard runtime now exposes normalized summary metadata, fires `iris.dashboard_updated` on initial load/live refresh, materializes a managed storage-Lovelace dashboard from backend schema, and live-refreshes collection-backed cards from the runtime store
- backend projector now handles current HA-facing `indicator_updated` and concrete pattern state variants in addition to the initial asset/prediction/portfolio families
- command execution now works end-to-end for the first real command slice, including backend-backed `switch/select` writes and live `operation_update`
- shared contract fixtures are now exercised from backend and integration tests, so drift is no longer only path-level
- delivery automation now includes submodule pin verification and a manual PR workflow for updating `ha/integration`

---

## What Is Not Done Yet

- no functional gaps remain inside the agreed HA scope; only normal version maintenance and future UX expansion remain

---

## Current Risks

- the integration now depends on Python `3.14.2+` because `Home Assistant 2026.3.1` requires it, so local dev/CI environments must provide that interpreter explicitly
- delivery is now split across two repos, which makes compatibility/guard automation more important because backend and integration can now drift independently
- if backend protocol evolves now, progress doc must be updated manually to avoid drift

---

## Optional Follow-up

1. Periodically bump and verify the isolated Home Assistant matrix beyond `2026.3.1`
2. Add richer custom cards or panel rendering if built-in Lovelace cards stop being sufficient for future collection-heavy surfaces

---

## Quick Verification Commands

```bash
cd backend
uv run ruff check src/apps/integrations/ha src/core/bootstrap/lifespan.py ../backend/tests/apps/integrations/test_ha_views.py
```

```bash
REDIS_URL=redis://127.0.0.1:56379/0 \
DATABASE_URL=postgresql+psycopg://iris:iris@127.0.0.1:5432/iris \
python -m pytest backend/tests/apps/integrations/test_ha_views.py -q
```

```bash
uv run ruff check --config backend/pyproject.toml ha/integration/custom_components/iris
python -m compileall ha/integration/custom_components/iris
```

```bash
cd ha/integration
uv sync --all-groups
uv run ruff check custom_components tests
uv run pytest tests -q
```
