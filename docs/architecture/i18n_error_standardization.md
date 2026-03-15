# IRIS I18n And Error Standardization

Last updated: 2026-03-15

## Current iteration scope

This iteration covers:

- Phase 0 audit
- Phase 1 ADR alignment
- Phase 2 minimal canonical foundation
- Phase 3 API error rollout

This iteration does **not** attempt a big-bang migration of every backend endpoint, frontend screen or Home Assistant payload.

## Phase status

| Phase | Status | Notes |
| --- | --- | --- |
| 0. Audit | Complete | Repo-wide audit captured below. |
| 1. ADR alignment | Complete | Existing ADRs mapped; missing decision captured as ADR 0016 draft. |
| 2. Base infrastructure | Complete (pilot) | `core/i18n`, `core/errors`, `en/ru` catalogs, registry-backed typed errors, and HA command dispatch pilot added. |
| 3. API and backend rollout | In progress | API error boundary is locale-aware across briefs, explanations, notifications, system, patterns, signals, market-data, news, market-structure, control-plane and hypothesis endpoints. |
| 4. Frontend and integration alignment | Not started | Waiting on shared contracts from phase 3. |
| 5. Quality enforcement | Not started | Waiting on broader adoption surface. |
| 6. Observability and docs | Not started | Waiting on canonical error usage in runtime paths. |

## Phase 0 audit

### Backend error handling

Current repo state is mixed rather than canonical:

- `ApiErrorFactory` is already adopted in 32 backend call sites and provides a useful transport foundation.
- direct inline `HTTPException(...)` text is no longer present in the migrated backend API endpoints; remaining transport debt is concentrated in operation-status surfaces and non-API runtime flows.
- direct `ValueError` / `LookupError` / `RuntimeError` / `TypeError` with inline text still exists in 49 backend raise sites.
- transport contracts still expose text-first fields:
  - `backend/src/core/http/contracts.py` -> `AcceptedResponse.message`
  - `backend/src/core/http/operations.py` -> `error_message`, event `message`
  - `backend/src/apps/integrations/ha/schemas.py` -> `HAErrorRead.message`
- app-local error mapping is inconsistent:
  - most backend domains now translate to registry-backed localized API errors;
  - operation-store failures still persist `error_code + error_message`, not `message_key + params`;
  - several domain/application exceptions still do not expose structured params, so the new API boundary uses generic localized top-level messages for those paths instead of fully specific localized narration.

### Backend localization

Localization logic is duplicated and not yet platform-owned:

- locale normalization and resolution are duplicated in:
  - `backend/src/apps/briefs/language.py`
  - `backend/src/apps/explanations/language.py`
  - `backend/src/apps/notifications/services/humanization_service.py`
- backend settings still expose only `IRIS_LANGUAGE` / `Settings.language`; there is no canonical `default/supported/fallback locale` policy in core settings.
- deterministic human text still exists as inline templates:
  - `backend/src/apps/notifications/services/humanization_service.py`
  - `backend/src/apps/explanations/services/generation_service.py`
- existing AI/localization artifacts persist `language`, but do not use a shared translation registry or `message_key`.

### Frontend

Frontend currently has no i18n foundation:

- `frontend/package.json` has no i18n dependency or locale infrastructure.
- UI text is hardcoded inline across Vue pages and components; representative examples:
  - `frontend/src/pages/ControlPlane.vue`
  - `frontend/src/pages/Coins.vue`
  - `frontend/src/pages/CoinHistory.vue`
- frontend business/status semantics still rely on raw strings like `BUY`, `SELL`, `failed`, `active`, `shadow`, `throttled` without a shared translation contract.

### Home Assistant integration

HA is also mixed:

- static HA localization scaffolding exists:
  - `ha/integration/custom_components/iris/strings.json`
  - `ha/integration/custom_components/iris/translations/en.json`
- Russian HA static translations do not exist yet.
- HA runtime/client-side errors still use ad-hoc strings in:
  - `ha/integration/custom_components/iris/command_bus.py`
  - `ha/integration/custom_components/iris/services.py`
  - `ha/integration/custom_components/iris/button.py`
  - `ha/integration/custom_components/iris/switch.py`
  - `ha/integration/custom_components/iris/select.py`
- backend HA catalog and dashboard text is still hardcoded in `backend/src/apps/integrations/ha/application/services.py`.

### Config validation and magic strings

Representative text-first validation and status debt still exists in:

- `backend/src/core/settings/base.py`
- `backend/src/apps/integrations/ha/application/control_state.py`
- `backend/src/core/ai/prompt_policy.py`
- multiple app services that raise inline validation messages
- frontend/API contracts that expose raw decision/status enums without a translation boundary

These are not all defects to rewrite immediately, but they are tracked migration targets.

### Logging and observability

Observability is not yet aligned with the target architecture:

- logging is mostly freeform and message-first;
- structured persistence logs exist, but error logs generally do not carry `error_code`, `message_key`, `domain`, `locale` or fallback metadata;
- there are no translation metrics, registry consistency metrics or locale fallback counters.

### Documentation

Existing docs already define important direction:

- `docs/iso/backend-business-localization-plan.md`
- `docs/iso/http-endpoint-refactor-audit.md`
- `docs/ha/adr-0001-ha-integration-architecture.md`

One audit note: `docs/iso/backend-business-localization-plan.md` says HA integration does not yet have `strings.json` / `translations`; that statement is now outdated because English HA static translation files exist.

## Phase 1 ADR alignment

Relevant accepted architecture decisions already in force:

- ADR 0012: services return typed domain contracts, not transport payloads.
- ADR 0005: analytical API semantics require stable transport behavior and cache-aware boundary decisions.
- ADR 0015: shared platform capabilities should live in `core`, not as app-specific exceptions.
- HA integration architecture note: backend owns catalog/runtime/business payloads; HA owns static integration UX surfaces.
- `docs/iso/backend-business-localization-plan.md`: boundary-localized narration, locale resolution order, and transport-safe rollout constraints.

Missing ADR-level decision before this iteration:

- there was no dedicated ADR for unified error taxonomy + registry + boundary localization as a shared platform layer.

Action taken in this iteration:

- added ADR draft `docs/architecture/adr/0016-error-taxonomy-and-boundary-localization.md`.

## Phase 2 minimal canonical change

### Added foundation

New shared backend infrastructure:

- `backend/src/core/i18n/*`
  - locale policy contracts
  - locale normalization / `Accept-Language` parsing
  - deterministic translator with fallback and interpolation checks
  - translation catalogs for `en` and `ru`
- `backend/src/core/errors/*`
  - typed error taxonomy
  - centralized error registry with duplicate protection
  - registry-backed `PlatformError` base class
  - canonical definitions for `internal_error`, `resource_not_found`, `validation_failed`, conflict/auth/policy/locked errors, HA command errors, and control-plane boundary errors
- `backend/src/core/http/errors.py`
  - adapter methods to translate `PlatformError` into the existing `ApiError` wire shape without changing the current transport contract
  - localized `ApiErrorDetail` metadata with `message_key`, `message_params` and `locale`

### Pilot migration

First consumer migrated to the new standard:

- `backend/src/apps/integrations/ha/errors.py`
- `backend/src/apps/integrations/ha/application/services.py`
- `backend/src/apps/integrations/ha/api/websocket_endpoints.py`

What changed in the pilot:

- HA command dispatch now raises typed registry-backed errors instead of ad-hoc inline strings for:
  - command not available
  - invalid payload
- message text is rendered from `message_key` via `core/i18n`
- machine-readable `details` now carry structured expectations such as `expected` and `allowed_values`
- current HA/WebSocket wire contract remains backward-compatible at the shape level (`code` + `message` + `details` + `retryable`)

### Verification

Verified in isolated mode without project `conftest`:

- `PYTHONPATH=backend pytest --noconftest backend/tests/core/test_i18n.py backend/tests/core/test_error_registry.py backend/tests/apps/integrations/test_ha_errors.py -q`
- result: `9 passed`

Project-native test suites are currently blocked by environment/runtime dependencies in this workspace:

- backend `conftest` expects reachable Redis/PostgreSQL services
- one fixture path also hits duplicate prompt seed state while bootstrapping test DB contents

Those failures are environment-related and not caused by the new isolated foundation tests.

## Phase 3 API rollout

### Added API locale boundary

Current API rollout now uses a shared request-aware locale resolver:

- `backend/src/core/http/deps.py`

Behavior:

- `language` and `locale` query params are normalized through shared `core/i18n`
- `X-IRIS-Locale` and `Accept-Language` are respected at the API boundary
- if the request provides no locale hint, the effective locale falls back to `Settings.language`

This keeps translation out of persistence and out of domain/application storage.

### Enriched API error contract

The existing `ApiError` transport shape was extended, not replaced:

- `message_key`
- `message_params`
- `locale`
- `domain`
- `category`
- `http_status`
- `severity`
- `safe_to_expose`
- detail-level `message_key`
- detail-level `message_params`
- detail-level `locale`

This was done in:

- `backend/src/core/http/errors.py`

Result:

- current clients still receive `code` + `message`
- newer clients can align on stable machine-readable metadata without parsing localized text

### Migrated API endpoints

This wave removed the remaining direct `HTTPException(detail=\"...\")` endpoints and moved major backend API domains onto registry-backed localized errors:

- `backend/src/apps/briefs/api/*`
- `backend/src/apps/explanations/api/*`
- `backend/src/apps/notifications/api/*`
- `backend/src/apps/system/api/operation_endpoints.py`
- `backend/src/apps/patterns/api/*`
- `backend/src/apps/signals/api/*`
- `backend/src/apps/market_data/api/*`
- `backend/src/apps/news/api/*`
- `backend/src/apps/market_structure/api/*`
- `backend/src/apps/control_plane/api/*`
- `backend/src/apps/hypothesis_engine/api/*`

Boundary-localized error helpers were added in:

- `backend/src/apps/briefs/api/errors.py`
- `backend/src/apps/explanations/api/errors.py`
- `backend/src/apps/notifications/api/errors.py`
- `backend/src/apps/patterns/api/errors.py`
- `backend/src/apps/signals/api/errors.py`
- `backend/src/apps/market_data/api/errors.py`
- `backend/src/apps/news/api/errors.py`
- `backend/src/apps/market_structure/api/errors.py`
- `backend/src/apps/control_plane/api/errors.py`
- `backend/src/apps/hypothesis_engine/api/errors.py`

Additional canonicalization in this wave:

- central error registry now carries stable definitions for `duplicate_request`, `invalid_state_transition`, `authentication_failed`, `authorization_denied`, `policy_denied`, `concurrency_conflict`, `integration_unreachable`, `prompt_veil_locked`, `invalid_access_mode`, `control_mode_required`, `control_token_invalid`
- control-plane detail payloads are now localized and expose machine-readable detail-level translation metadata
- request locale is threaded into command translators through closures instead of changing `execute_command(...)` transport contracts
- market-structure ingest result errors no longer synthesize top-level messages from `reason.replace(...)`

### Verification

Additional isolated verification for this phase:

- `PYTHONPATH=backend pytest --noconftest backend/tests/core/test_i18n.py backend/tests/core/test_http_locale.py backend/tests/core/test_error_registry.py backend/tests/apps/integrations/test_ha_errors.py backend/tests/apps/briefs/test_brief_api_errors.py backend/tests/apps/explanations/test_explanation_api_errors.py backend/tests/apps/notifications/test_notification_api_errors.py backend/tests/apps/patterns/test_pattern_api_errors.py backend/tests/apps/signals/test_signal_api_errors.py backend/tests/apps/market_data/test_market_data_api_errors.py backend/tests/apps/news/test_news_api_errors.py backend/tests/apps/market_structure/test_market_structure_api_errors.py backend/tests/apps/control_plane/test_control_plane_api_errors.py backend/tests/apps/hypothesis_engine/test_hypothesis_api_errors.py -q`
- result: `22 passed`

## What is done

- audit recorded and centralized
- ADR alignment completed
- missing ADR captured as draft 0016
- minimal shared i18n and error foundation added
- first cross-layer pilot migrated in HA command dispatch
- API locale boundary now resolves language from query/header/settings instead of app-local API helpers
- API error payloads now expose shared machine fields alongside localized text
- direct string-first API `HTTPException` paths across the current backend endpoint surface were migrated
- remaining backend domain `api/errors.py` translators were moved off `message=str(exc)` and onto registry-backed `PlatformError`
- `ApiErrorDetail` now supports localized detail metadata and is used in control-plane concurrency/access-mode errors
- control-plane header/auth/policy boundary errors now have stable registry-backed error codes

## What remains

Priority next steps for phase 3:

- replace text-first operation status/event messages in `core/http/operation_store.py` with `message_key + params`
- replace duplicated app-local language helpers with `core/i18n`
- start replacing text-first backend narration in high-priority deterministic surfaces with `message_key + params`
- refine domain exceptions that currently only expose exception type, so API localization can preserve domain-specific detail without falling back to generic top-level registry messages

Priority next steps for phase 4:

- add frontend i18n foundation and move hardcoded UI text onto translation catalogs
- add HA `ru` static translations
- align frontend/HA consumption with shared `error_code` / `message_key`

## Risks and legacy zones

- operation status contracts are still text-first and will require a dedicated migration wave
- frontend has no i18n runtime yet, so backend/shared contracts alone do not solve UI localization
- notification/explanation/brief services still use duplicated locale helpers and string templates
- HA backend catalog/dashboards still hardcode labels in Python
- several domain exceptions still carry human English text internally and need structured params before their localized API messages can become fully domain-specific
- translation linting, locale-aware CI, and observability are not implemented yet
