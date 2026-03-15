# IRIS I18n And Error Standardization

> Historical rollout note.
> Use [ADR index](../adr/index.md), [Terminology](../terminology.md), and [Backend Business Localization Plan](../../delivery/backend-business-localization-plan.md) for the current source of truth.

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
| 1. ADR alignment | Complete | Accepted ADR 0017 and ADR 0018 are now the source of truth; ADR 0016 remains draft background only. |
| 2. Base infrastructure | Complete (canonical slice) | `core/i18n`, `core/errors`, external `en/ru` YAML catalogs, global locale policy, registry-backed typed errors, and HA command dispatch pilot added. |
| 3. API and backend rollout | In progress | API and HA error boundaries now localize from `message_key + params` using the global settings locale across the migrated backend domains. |
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
  - `backend/src/apps/integrations/ha/schemas.py` -> `HAErrorRead.message` is still present for presentation, but the contract now also carries `message_key`, `message_params` and `locale`
- app-local error mapping is inconsistent:
  - most backend domains now translate to registry-backed localized API errors;
  - operation-store lifecycle/error persistence is now machine-first (`message_key + params` and `error_message_key + params`), but several domain result producers still only emit generic status/reason values, so some localized operation failures remain generic;
  - several domain/application exceptions still do not expose structured params, so the new API boundary uses generic localized top-level messages for those paths instead of fully specific localized narration.

### Backend localization

Localization logic is duplicated and not yet platform-owned:

- locale normalization and resolution are duplicated in:
  - `backend/src/apps/briefs/language.py`
  - `backend/src/apps/explanations/language.py`
  - `backend/src/apps/notifications/services/humanization_service.py`
- canonical global locale policy now exists in `backend/src/core/i18n/locale_policy.py`; this iteration also added shared context-language resolution in `backend/src/core/i18n/context.py`, and the old app-local helpers now act as thin bridges over that core path.
- deterministic human text for `notifications` and `explanations` now renders from shared catalogs; remaining inline deterministic narration debt is concentrated outside those two services.
- operation/system read-side localization is now centralized in `backend/src/core/http/operation_localization.py`, but deterministic narration outside transport boundaries still bypasses the shared translator.
- persisted AI/localization artifacts no longer store row-level `language`; locale now lives only in `rendered_locale` inside the canonical presentation envelope.

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
- `ha/integration/custom_components/iris/translations/ru.json` now exists for the static integration UX surface.
- HA runtime/client-side errors still use ad-hoc strings in:
  - `ha/integration/custom_components/iris/command_bus.py`
  - `ha/integration/custom_components/iris/services.py`
  - `ha/integration/custom_components/iris/button.py`
  - `ha/integration/custom_components/iris/switch.py`
  - `ha/integration/custom_components/iris/select.py`
- backend HA catalog and dashboard labels now render from shared `ha.*` translation keys in the centralized backend catalogs.

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

- `docs/delivery/backend-business-localization-plan.md`
- `docs/delivery/http-endpoint-refactor-audit.md`
- `docs/home-assistant/notes/integration-architecture.md`

One audit note: `docs/delivery/backend-business-localization-plan.md` says HA integration does not yet have `strings.json` / `translations`; that statement is now outdated because English HA static translation files exist.

## Phase 1 ADR alignment

Relevant accepted architecture decisions already in force:

- ADR 0012: services return typed domain contracts, not transport payloads.
- ADR 0005: analytical API semantics require stable transport behavior and cache-aware boundary decisions.
- ADR 0015: shared platform capabilities should live in `core`, not as app-specific exceptions.
- ADR 0017: localization uses a global settings-driven locale model; `Accept-Language` and request-local overrides are out of scope.
- ADR 0018: message keys use the accepted `error.*`, `ui.*`, `notification.*`, `brief.*`, `report.*`, `ha.*`, `doc.*`, `system.*` taxonomy.
- HA integration architecture note: backend owns catalog/runtime/business payloads; HA owns static integration UX surfaces.
- `docs/delivery/backend-business-localization-plan.md`: boundary-localized narration, locale resolution order, and transport-safe rollout constraints.

Action taken in this iteration:

- aligned implementation to accepted ADR 0017 and ADR 0018.
- kept ADR draft `docs/architecture/adr/0016-error-taxonomy-boundary-localization.md` only as historical rollout background, not as active source of truth.
- added ADR draft `docs/architecture/adr/0021-generated-presentation-artifact-ownership.md` to capture the persisted ownership model for `descriptor_bundle` vs `generated_text` artifacts, because that storage distinction is not fully specified by ADR 0017/0018.

## Phase 2 minimal canonical change

### Added foundation

New shared backend infrastructure:

- `backend/src/core/i18n/*`
  - locale policy contracts
  - global locale policy builder aligned with `Settings.language`
  - deterministic locale resolver without request/header negotiation
  - deterministic translator with fallback and interpolation checks
  - external versioned translation catalogs for `en` and `ru`
- `backend/src/core/errors/*`
  - typed error taxonomy
  - centralized error registry with duplicate protection
  - registry-backed `PlatformError` base class carrying structured metadata, not localized user text
  - canonical definitions for `internal_error`, `resource_not_found`, `validation_failed`, conflict/auth/policy/locked errors, HA command errors, and control-plane boundary errors
- `backend/src/core/http/errors.py`
  - adapter methods that localize `PlatformError` only at the transport boundary without changing the current `ApiError` shape
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
- message text is rendered from `message_key` via `core/i18n` only when HA transport payloads are built
- machine-readable `details` now carry structured expectations such as `expected` and `allowed_values`
- HA/WebSocket runtime error payloads now also carry `message_key`, `message_params` and `locale`

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

Current API rollout now uses the accepted global locale model:

- `backend/src/core/http/deps.py`

Behavior:

- request/query/header locale overrides are ignored
- effective locale resolves from `Settings.language`
- fallback locale remains `en`

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
- registry `message_key` values were renamed to ADR-0018-compliant `error.*` taxonomy
- translation catalogs moved from Python modules to versioned external YAML files with `description` and `message`
- `PlatformError` no longer renders localized user text; transport adapters and HA bridge now localize from `message_key + params`
- control-plane detail payloads are now localized and expose machine-readable detail-level translation metadata
- HA runtime error payloads now expose `message_key`, `message_params` and `locale` symmetrically with backend API errors
- market-structure ingest result errors no longer synthesize top-level messages from `reason.replace(...)`

### Operation lifecycle boundary rollout

This iteration also moved async operation status/event surfaces onto the same presentation-only localization model:

- `backend/src/core/http/operation_store.py` now persists lifecycle/error metadata as `message_key + message_params` and `error_message_key + error_message_params` instead of storing localized strings in Redis.
- `backend/src/core/http/contracts.py`, `backend/src/core/http/operations.py`, and `backend/src/apps/integrations/ha/schemas.py` now expose machine-readable operation fields alongside presentation text:
  - `message_key`
  - `message_params`
  - `locale`
  - `error_message_key`
  - `error_message_params`
  - `error_locale`
- `backend/src/core/http/operation_localization.py` centralizes read-time localization for:
  - system operation status/result/events
  - accepted background-job responses
  - HA operation update/status payloads
- `backend/src/apps/system/api/*` and `backend/src/apps/integrations/ha/application/services.py` now localize operation messages only when building transport payloads.
- `backend/src/apps/market_data/api/job_endpoints.py` was aligned with the same locale-aware boundary after a missed `market_data_error_to_http(..., locale=...)` path was found during verification.

### Deterministic narration rollout

This iteration also removed the last hardcoded multilingual Python branches from the deterministic fallback layer:

- `backend/src/core/i18n/context.py` now owns shared context-language normalization and effective-language resolution for app services.
- `backend/src/apps/briefs/language.py` and `backend/src/apps/explanations/language.py` now delegate to the shared `core/i18n` helper instead of maintaining parallel locale logic.
- `backend/src/apps/notifications/services/humanization_service.py` now renders deterministic fallback notifications from catalog keys under:
  - `notification.*`
- `backend/src/apps/explanations/services/generation_service.py` now renders deterministic fallback explanation titles/body/bullets from catalog keys under:
  - `brief.explanation.*`
- shared `en` / `ru` catalogs now contain deterministic fallback texts for:
  - notification titles/messages
  - explanation titles, bodies, and bullet variants

Result:

- deterministic fallback narration for notifications and explanations is no longer source-of-truth text in Python code;
- adding another language for those surfaces now requires only catalog expansion, not business-logic edits;
- the rollout now treats persisted presentation artifacts as canonical envelopes rather than locale-specific rendered text rows.

### Canonical presentation artifact storage

This iteration moved persisted `notifications`, `explanations`, and `briefs` onto an explicit canonical presentation envelope:

- ORM/storage schema now includes:
  - `content_kind`
  - `content_json`
- accepted `content_kind` values are:
  - `descriptor_bundle`
  - `generated_text`
- `descriptor_bundle` stores `message_key + params` field descriptors in canonical JSON form.
- `generated_text` stores a rendered presentation snapshot plus `rendered_locale`.
- new writes no longer use `context_json.localization` as the active storage contract.
- legacy text columns (`title`, `message`, `explanation`, `summary`, `bullets_json`) and persisted artifact `language` columns have now been physically removed from the ORM schema in favor of the envelope.
- read presenters now resolve content from validated `content_json`, with fallback to old `context_json.localization` only for transitional rows that predate the canonical envelope backfill.

Storage identity is also now language-agnostic:

- `ai_notifications` are unique by `source_event_type + source_event_id`
- `ai_explanations` are unique by `explain_kind + subject_id`
- `ai_briefs` are unique by `brief_kind + scope_key`
- `notifications` event handling and `explanations` generation no longer consume explicit per-call/per-event language overrides; effective locale comes only from global settings
- `briefs` generation and brief job deduplication/locking now also ignore explicit per-call language overrides and resolve locale only from global settings
- explanation job deduplication and task locks no longer include language
- brief job deduplication and task locks no longer include language
- `notification_created` event payloads no longer leak `language` into the event bus
- brief/explanation accepted job contracts and operation result payloads now use `rendered_locale` instead of legacy `language`

Migration work included:

- backfilling existing rows into `content_json`
- collapsing historic locale duplicates into a single canonical row per business entity, preferring descriptor-backed rows when both existed
- replacing the old locale-scoped unique indexes with canonical unique indexes that do not include `language`
- dropping legacy persisted artifact `language` and rendered-text columns after the envelope backfill completed

Result:

- persisted notifications/explanations/briefs are now one-row-per-entity rather than one-row-per-locale;
- deterministic descriptor-backed content is re-rendered on the presentation boundary from shared catalogs;
- freeform AI-generated content is now explicitly governed as `generated_text` presentation snapshot content instead of accidental text-first storage;
- locale changes no longer create duplicate rows for these artifact types;
- persisted artifact read contracts no longer expose legacy row language and instead expose only `rendered_locale` from the presentation envelope.

### Verification

Additional isolated verification for this phase:

- `PYTHONPATH=backend pytest --noconftest backend/tests/core/test_i18n.py backend/tests/core/test_http_locale.py backend/tests/core/test_error_registry.py backend/tests/apps/integrations/test_ha_errors.py backend/tests/apps/briefs/test_brief_api_errors.py backend/tests/apps/explanations/test_explanation_api_errors.py backend/tests/apps/notifications/test_notification_api_errors.py backend/tests/apps/patterns/test_pattern_api_errors.py backend/tests/apps/signals/test_signal_api_errors.py backend/tests/apps/market_data/test_market_data_api_errors.py backend/tests/apps/news/test_news_api_errors.py backend/tests/apps/market_structure/test_market_structure_api_errors.py backend/tests/apps/control_plane/test_control_plane_api_errors.py backend/tests/apps/hypothesis_engine/test_hypothesis_api_errors.py -q`
- result: `22 passed`
- `PYTHONPATH=backend pytest --noconftest backend/tests/core/test_i18n.py backend/tests/core/test_error_registry.py backend/tests/core/test_operation_localization.py backend/tests/apps/integrations/test_ha_errors.py backend/tests/apps/market_data/test_views.py::test_market_data_view_branches -q`
- result: `15 passed`
- `PYTHONPATH=backend pytest --noconftest backend/tests/core/test_i18n.py backend/tests/core/test_i18n_context.py backend/tests/apps/notifications/test_humanization_service.py backend/tests/apps/explanations/test_generation_service_rendering.py -q`
- result: `11 passed`
- `PYTHONPATH=backend pytest --noconftest backend/tests/core/test_i18n.py backend/tests/core/test_i18n_context.py backend/tests/core/test_i18n_descriptors.py backend/tests/apps/notifications/test_humanization_service.py backend/tests/apps/notifications/test_notification_presenters.py backend/tests/apps/explanations/test_generation_service_rendering.py backend/tests/apps/explanations/test_explanation_presenters.py -q`
- result: `16 passed`
- `PYTHONPATH=backend pytest --noconftest backend/tests/core/test_i18n.py backend/tests/core/test_i18n_context.py backend/tests/core/test_i18n_descriptors.py backend/tests/apps/notifications/test_humanization_service.py backend/tests/apps/notifications/test_notification_presenters.py backend/tests/apps/notifications/test_notification_service_storage.py backend/tests/apps/explanations/test_generation_service_rendering.py backend/tests/apps/explanations/test_explanation_presenters.py backend/tests/apps/explanations/test_explanation_service_storage.py -q`
- result: `20 passed`
- `PYTHONPATH=backend pytest --noconftest backend/tests/core/test_i18n.py backend/tests/core/test_i18n_context.py backend/tests/core/test_i18n_descriptors.py backend/tests/core/test_i18n_presentation.py backend/tests/apps/notifications/test_humanization_service.py backend/tests/apps/notifications/test_notification_presenters.py backend/tests/apps/notifications/test_notification_service_storage.py backend/tests/apps/explanations/test_generation_service_rendering.py backend/tests/apps/explanations/test_explanation_presenters.py backend/tests/apps/explanations/test_explanation_service_storage.py -q`
- result: `24 passed`
- `PYTHONPATH=backend pytest --noconftest backend/tests/core/test_i18n.py backend/tests/core/test_i18n_presentation.py backend/tests/apps/briefs/test_brief_storage.py backend/tests/apps/briefs/test_brief_presenters.py -q`
- result: `8 passed`
- `PYTHONPATH=backend pytest --noconftest backend/tests/core/test_i18n_presentation.py backend/tests/apps/notifications/test_notification_service_storage.py backend/tests/apps/explanations/test_explanation_service_storage.py backend/tests/apps/briefs/test_brief_storage.py backend/tests/apps/notifications/test_notification_presenters.py backend/tests/apps/explanations/test_explanation_presenters.py backend/tests/apps/briefs/test_brief_presenters.py -q`
- result: `14 passed`

Brief DB-backed integration tests still require the full project fixture stack (`async_db_session`, `api_app_client`) and were not rerun in isolated `--noconftest` mode.

## What is done

- audit recorded and centralized
- ADR alignment completed
- accepted ADR 0017 and ADR 0018 are now explicitly reflected in the implementation
- minimal shared i18n and error foundation added
- first cross-layer pilot migrated in HA command dispatch
- API locale boundary now resolves language only from global settings
- API error payloads now expose shared machine fields alongside localized text
- direct string-first API `HTTPException` paths across the current backend endpoint surface were migrated
- remaining backend domain `api/errors.py` translators were moved off `message=str(exc)` and onto registry-backed `PlatformError`
- `ApiErrorDetail` now supports localized detail metadata and is used in control-plane concurrency/access-mode errors
- control-plane header/auth/policy boundary errors now have stable registry-backed error codes
- shared catalogs are now external versioned YAML files with descriptions
- HA runtime error payloads are now aligned with backend error machine fields
- async operation storage is now machine-first, and system API / HA operation payloads localize only on read from shared message catalogs
- accepted background-job payloads now expose operation `message_key` metadata consistently with system status/event payloads
- duplicated app-local language resolution for briefs/explanations/notifications now routes through shared `core/i18n`
- deterministic fallback narration in notifications and explanations now renders from shared message catalogs instead of inline multilingual Python branches
- deterministic notification/explanation artifacts now persist descriptor metadata and are localized again at read time instead of treating stored text as canonical
- notifications and explanations now persist canonical `content_kind + content_json` envelopes, and legacy rendered text fields are no longer present in the active schema
- notifications/explanations storage identity is now one-row-per-entity instead of one-row-per-locale
- briefs now persist canonical `content_kind + content_json` envelopes, and legacy rendered text fields are no longer present in the active schema
- briefs storage identity is now one-row-per-entity instead of one-row-per-locale
- explanation job deduplication/task locking no longer depends on locale
- brief job deduplication/task locking no longer depends on locale
- `notification_created` event payload no longer carries locale-specific data
- persisted artifact read contracts and accepted job contracts no longer expose legacy row `language`; they now expose `rendered_locale`
- canonical presentation envelope validation now exists in `core/i18n/presentation.py` and is covered by unit tests
- HA catalog entity names, command names and dashboard titles now render from shared backend translation catalogs instead of hardcoded Python strings
- HA integration now includes static Russian translations for config-flow UX
- translation catalog validation/coverage tooling now exists in `core/i18n/validators.py`, `backend/scripts/export_i18n_coverage.py`, `backend/scripts/check_i18n_catalogs.py`, committed `docs/_generated/i18n-coverage.md`, and CI `make i18n-check`

## What remains

Priority next steps for phase 3:

- start replacing text-first backend narration in high-priority deterministic surfaces with `message_key + params`
- migrate operation result producers that still only return generic `status` / `reason` / `error_code` values so read-time localization can preserve richer domain-specific messages
- refine domain exceptions that currently only expose exception type, so API localization can preserve domain-specific detail without falling back to generic top-level registry messages

Priority next steps for phase 4:

- add frontend i18n foundation and move hardcoded UI text onto translation catalogs
- align frontend/HA consumption with shared `error_code` / `message_key`

## Risks and legacy zones

- operation transport contracts still retain localized `message` / `error_message` fields for backward-compatible presentation, even though the backing store is now machine-first
- frontend has no i18n runtime yet, so backend/shared contracts alone do not solve UI localization
- generated text remains locale-specific snapshot content by design, so locale switching for AI-generated artifacts still requires explicit regeneration/replacement if a new language snapshot is needed
- several domain exceptions still carry human English text internally and need structured params before their localized API messages can become fully domain-specific
- observability for translation fallback/error metrics is not implemented yet
