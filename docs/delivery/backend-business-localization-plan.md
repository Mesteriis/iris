# Backend Business Localization Plan

## Goal

Define how IRIS should support multilingual user-facing behavior at the backend level so that:

- users can understand business narration in API responses, Home Assistant surfaces, event-like delivery surfaces, and operation-status flows;
- machine contracts remain canonical and automation-safe;
- accepted service/engine and presenter boundaries remain intact;
- localization fits the existing governance model instead of becoming a separate mini-architecture.

This document covers **backend business localization**, not frontend i18n.

## Architectural Context

The plan must work inside already accepted IRIS constraints:

- service layer and analytical engines are already separated;
- post-commit side effects are already explicit;
- runtime is event-driven and governed by control plane;
- HTTP API lives under OpenAPI, capability, and analytical cache governance;
- Home Assistant is an external automation and notification host;
- the AI layer is a separate capability and must not replace deterministic localization.

## Current Repository State

At the time of this plan, the repository still had several constraints that must be addressed explicitly rather than hidden under abstractions:

- signal and portfolio surfaces still depended on `reason: str` rather than formalized reason taxonomy;
- some API boundary contracts still re-exported app-level schemas too directly;
- HTTP cache semantics did not yet vary by language;
- settings exposed only a single `language` field rather than a richer locale policy;
- runtime stream messages still used text-first legacy payloads;
- the HA integration still consumed raw business reason text;
- HA static translations and backend business narration were not cleanly separated.

Therefore, localization cannot start from “translating strings.” It must start from canonical taxonomy and a transport-safe foundation.

## Problem

The backend mostly returned machine-oriented semantics:

- statuses and codes;
- reason or message text as free strings;
- operation messages as unstructured text;
- HA payloads and legacy bus messages without formalized descriptor models.

That is acceptable for automation, but insufficient for humans:

- users see system vocabulary instead of understandable messages;
- free-text reason fields are hard to translate and hard to stabilize;
- output language is not properly controlled in API cache semantics or HA delivery;
- translation and business truth can easily get mixed inside boundary code.

## Scope

This plan covers backend-owned human-facing text only:

- human-readable business messages in API responses;
- event, SSE, or push payloads that are not machine-only;
- persisted notifications or similar backend-owned artifacts;
- deterministic summaries and briefs that are not AI-generated.

This plan does not cover:

- frontend i18n;
- arbitrary user content translation from the database;
- AI-generated freeform translation as the primary mechanism;
- translation of machine identifiers such as `BUY`, `SELL`, `signal_created`, or `market_regime_changed`.

## Core Idea

The business logic itself is not translated.

What gets translated is **what the system tells a human about the results of that logic**.

Correct model for IRIS:

- machine outcome remains canonical;
- a formalized narration descriptor is built above it;
- the descriptor is rendered at the boundary in the requested locale;
- humans get understandable text while automation continues to operate on codes.

## Non-Negotiable Rules

### 1. Canonical Taxonomy First

Localization starts with formalized machine vocabulary, not free text.

Minimum canonical set:

- reason taxonomy
- message keys
- structured message params
- stable machine-readable error and status codes

If a domain still depends on `reason: str`, direct translation of that text is the wrong first step.

### 2. Machine Contracts Remain the Source of Truth

Automation, routing, policies, alerts, and downstream integrations must rely on canonical machine fields, not localized text.

### 3. Localization Does Not Live in Engines

Pure engines and deterministic domain math must not:

- accept locale;
- query translation catalogs;
- render user-facing text;
- format labels, percentages, or durations.

### 4. Localization Does Not Live in Orchestration Services as Inline Strings

Services may return codes, facts, and typed results, but they must not become scattered string builders.

### 5. Boundary Contracts Must Be Separate From App Schemas

Do not simply add `message_key`, `message`, or `message_params` to app-level schemas when those same schemas still act as domain or application forms.

Localization should enter through dedicated API or HA envelopes and presenter contracts.

### 6. One Narration System Per Surface

Avoid a parallel world with:

- a new descriptor-based API and HA layer;
- old text-first runtime messages;
- separate ad-hoc operation text.

Each surface needs one target narration model and a clear deprecation path for legacy text.

### 7. AI Is Not the Primary Translation Mechanism

AI may enrich explanation or humanize deterministic outcomes, but it must not replace the canonical descriptor layer.

## Migration Matrix for Legacy Fields

| Current field | Target form | Transitional state |
|---|---|---|
| `reason: str` | `reason_code` | `reason` remains temporarily as deprecated legacy text |
| `message: str` | `message_key` + `message_params` + optional rendered `message` | dual-field transitional contract is allowed on pilot surfaces |
| `status: str` | `status` | remains canonical |
| `decision: str` | `decision` | remains canonical |
| `text` in legacy bus | descriptor or explicit deprecated text field | legacy bus cleanup happens in a separate wave |

## Target Contract Model

### 1. Machine Outcome

Machine outcome remains typed, canonical, and language-neutral.

### 2. Message Descriptor

Above the machine outcome, build a deterministic narration descriptor:

- `message_key`
- `message_params`
- `surface`
- optional `variant`

`surface` exists so the same semantic message can be adapted to API, HA, notifications, or operation-status use without collapsing everything into one ambiguous key.

`variant` exists so short, normal, and extended forms can coexist explicitly.

### 3. Localized Render

Boundary adapters render:

```text
message_key + params + locale -> human text
```

### 4. Final User-Facing Payload

The final payload may contain both:

- machine fields
- rendered human text

`message_params` should carry semantics, not preformatted display artifacts.

## Target Layer Model

### 1. `core/i18n`

Backend localization needs a shared core:

- supported locale set
- locale resolver
- translator
- formatter for numbers, percentages, counts, dates, and durations
- fallback policy

### 2. Domain Narratives

Domains that need human-readable backend output should provide a pure narrative layer.

Role:

- accept typed domain result or read model;
- return `MessageDescriptor`;
- perform no IO;
- know nothing about HTTP, HA, Redis Streams, or AI providers.

### 3. Boundary Adapters

Localization rendering lives in presenters and adapters.

They:

- take `MessageDescriptor`;
- choose locale;
- call the translator;
- add rendered text to response or event payload.

### 4. API-Localized Contracts Separate From App Schemas

Pilot rollout and long-term rollout must explicitly separate:

- app and domain result contracts
- localized API envelopes

## Locale and Configuration Policy

### Canonical Locale Model

Supported locales should be modeled in proper BCP 47 form.

`ua` is not a canonical language tag and should not be emitted as output.

Migration path:

- accept `ua` temporarily as input alias;
- normalize it to `uk`;
- never store or emit `ua` as effective locale.

### Repo-Level Settings

A single `IRIS_LANGUAGE`-style field is not enough forever.

Target configuration should support:

- instance default language;
- fallback language;
- normalization policy;
- future expansion for more locale-aware behavior.

The current `language` field may remain as a compatibility alias during migration.

### Resolution Order

1. explicit locale override on the surface
2. stored user or integration preference when available
3. `settings.language`
4. fallback locale

All input is normalized to the supported locale set.

### Surface-Specific Overrides

A minimal starting point may support:

- instance default language
- explicit override header such as `X-IRIS-Locale`

## Cache and OpenAPI Policy

Localization must not be layered onto current read endpoints without transport-safe semantics.

### 1. Stable Contract Per Endpoint

At the start, avoid dual-mode endpoint shapes.

Reasons:

- fixed `response_model` is part of governance;
- committed OpenAPI snapshots must stay stable;
- analytical cache semantics are not ready for ambiguous locale-dependent variance under one shape.

Practical rule:

- either an endpoint stays canonical-only;
- or it gets an explicit localized read contract.

### 2. Language-Aware Cache Semantics

As soon as an endpoint renders locale-dependent narration, caching must account for language.

Otherwise the system will return:

- the wrong language from cache;
- incorrect `304 Not Modified`;
- stale locale variants under the same `ETag`.

### 3. Snapshot Surfaces

Localization does not remove existing analytical snapshot requirements.

Locale becomes one more dimension of the transport contract.

## Formatting Policy

Localization without formatting policy collapses quickly.

Define formally:

- number formatting
- percentage formatting
- signed deltas
- counts
- date and datetime presentation
- durations

The rule is simple:

- `message_params` carry semantics;
- translator and formatter layers handle display formatting.

## Persisted Artifacts Policy

Storing only `message_key + params` is useful but not enough for audit-heavy surfaces.

If the catalog changes later, the same historical artifact might render differently.

Therefore persisted notifications, operation history, and similar surfaces need at least one of:

- `catalog_version` alongside the descriptor
- a materialized render snapshot
- or both for especially audit-sensitive surfaces

## HA-Specific Policy

### 1. HA-Side Static Integration Strings

Strings like config-flow labels, static UI labels, and integration chrome are the responsibility of the HA integration itself.

### 2. Backend-Rendered Business Narration

Business narration about domain outcomes is the responsibility of the backend.

HA should not rebuild business messages from raw fields.

### HA Payload Rule

HA-facing payloads should contain:

1. machine truth for automation;
2. descriptor or localized narration for humans.

The current text-first transmission of business `reason` in HA event payloads is considered legacy and must be migrated.

## Legacy Message Bus Policy

The runtime stream message layer still contains a text-first model.

That cannot remain as a second independent narration system.

Plan requirement:

- either migrate legacy message bus payloads to descriptor-based shape;
- or put them on an explicit deprecation path and remove them from canonical human-facing surfaces.

## Operations and Shared HTTP Contracts

Operation and status narration are in scope, but **not in the pilot wave**.

Current shared contracts still include text-first fields like `message: str`.

Implications:

- localizing operation and status flows requires changes to shared HTTP contracts;
- that should not be mixed into the first presenter-layer pilot.

## Relation to the AI Layer

AI humanization must not be the first step in multilingual support.

First build deterministic backend narration.

Only then may AI:

- rephrase;
- extend explanation;
- adapt tone;
- build briefs on top of the canonical descriptor layer.

## Why Not `gettext` Like Django

Django-style `gettext` is good for:

- HTML templates
- static UI strings
- view-layer translation in a traditional web app

But it is not the right primary architecture for IRIS because:

- the backend is typed API-first, not HTML-first;
- value lives in business narration rather than static page templates;
- IRIS needs machine codes and localized text at the same time;
- transport-safe cache and OpenAPI policy matter as much as string lookup.

The better path for IRIS is:

- descriptor-based narration
- a typed translator core
- richer ICU/Babel-like formatting later if needed

## Proposed File Structure

Practical target:

```text
backend/src/core/i18n/
  contracts.py
  locales.py
  resolver.py
  translator.py
  formatter.py
  catalogs/

backend/src/apps/<domain>/
  narratives.py
  api/
    presenters.py
    localized_contracts.py
```

If a domain does not need a full package, `narratives.py` is acceptable, but not inline strings inside services.

## Rollout Plan

### Wave 0. Canonical Taxonomy First

- define reason taxonomy
- keep legacy `reason` only as deprecated compatibility
- fix migration matrix for shared fields

### Wave 1. Transport-Safe Foundations

- add `core/i18n` contracts, translator, resolver, and formatter
- fix catalog format
- define repo-level locale settings
- normalize `ua -> uk`
- update cache semantics for locale-aware surfaces

### Wave 2. Presenter-Layer Pilot

- start with `signals` and `portfolio`
- add pure narrative descriptor builders
- separate localized API contracts from app schemas
- localize through presenters only

### Wave 3. HA and Legacy Bus Cleanup

- migrate HA-facing business payloads to descriptors
- decide which strings remain HA-side static strings
- remove reliance on raw `reason`
- migrate or explicitly deprecate legacy message bus text

### Wave 4. Operations and Shared HTTP Contracts

- localize accepted, job, and operation narration
- update shared HTTP contracts
- define persistence policy for operation history render snapshots

### Wave 5. Expansion

- extend to `market_structure`, `anomalies`, `predictions`, and `cross_market`
- connect the same locale contract to AI-derived surfaces
- forbid AI-only narration without a canonical descriptor underneath

## Architecture Checks

Once the layer stabilizes, useful automated checks include:

- services and engines do not import translator directly
- pilot domains no longer depend on raw `reason: str` as source of truth
- API-localized contracts stay separate from app schemas
- locale-aware endpoints use language-aware cache semantics
- catalogs cover required keys
- missing translations produce typed fallback instead of silent empty strings
- persisted audit-heavy artifacts carry `catalog_version` or materialized render snapshots

## Definition of Done

Backend business localization is considered correctly implemented only if:

- pilot domains no longer depend on raw `reason` as the canonical explanation field;
- machine contracts remain language-neutral;
- localized narration is built in a separate pure layer;
- localized API contracts are separate from app schemas and read models;
- locale is chosen formally and predictably;
- locale-aware reads do not break OpenAPI or cache semantics;
- HA receives both machine fields and human-readable business narration;
- legacy text-first runtime paths are either migrated or explicitly deprecated;
- the backend can render at least `ru/en/es/uk`;
- no domain engine knows about translation;
- the AI layer does not replace deterministic localization.

## Main Conclusion

For IRIS, the correct path is neither “translate reason strings directly” nor “sprinkle `_()` through services.”

The correct path is:

1. formalize canonical taxonomy;
2. add a transport-safe localization foundation;
3. localize boundary presenters on pilot domains;
4. only then move the model into HA, legacy bus, and shared operation surfaces.

That path is compatible with the current IRIS architecture and does not break the cleaned-up service/runtime boundaries.
