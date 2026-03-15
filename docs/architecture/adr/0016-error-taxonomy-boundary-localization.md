# ADR 0016: Error Taxonomy And Boundary Localization

## Status

Proposed

## Date

2025-03-10

## Context

IRIS already has a partial HTTP error foundation (`core/http/errors.py`) and a backend localization plan (`docs/iso/backend-business-localization-plan.md`), but the repo still has architectural gaps:

- typed errors are not centralized and many flows still raise string-first `ValueError`, `LookupError`, `HTTPException` or `HomeAssistantError`;
- stable `error_code` and `message_key` are not governed by a single registry;
- locale resolution is duplicated in app-local helpers instead of living in shared core infrastructure;
- frontend, backend and Home Assistant use different text ownership rules;
- transport surfaces still depend on freeform `message` / `error_message` fields as primary user-facing output.

The rollout needs a canonical platform layer that aligns with existing ADRs instead of creating a parallel architecture.

## Decision

IRIS introduces a shared platform foundation for error taxonomy and boundary localization.

The practical rules are:

- every registered platform error must define `error_code`, `message_key`, `domain`, `category`, `http_status`, `severity`, `retryable` and `safe_to_expose`;
- registry ownership lives in `src/core/errors`, with duplicate protection for both `error_code` and `message_key`;
- boundary localization lives in `src/core/i18n`, with deterministic locale normalization, locale resolution, interpolation and fallback behavior;
- machine-readable contracts remain canonical; localized text is rendered from `message_key + params`, not used as the source of truth;
- backend API, frontend clients and Home Assistant integration must converge on the same canonical `error_code` and `message_key` vocabulary;
- static Home Assistant UI strings remain HA-owned (`strings.json` / `translations/*`), while backend-owned business narration remains backend-owned;
- rollout is incremental: existing `code/message` wire contracts can remain transitional, but all new migrations must use the registry-backed platform layer instead of adding new ad-hoc strings.

## Consequences

This creates a migration-safe path toward a unified error and localization model:

- backend can migrate endpoint-by-endpoint without a big-bang rewrite;
- frontend and Home Assistant can align on shared machine-readable contracts before full UI localization;
- translation linting, registry validation and locale-aware tests become mechanically enforceable;
- observability can attach error and locale metadata without parsing human text;
- legacy text-first contracts remain a tracked migration debt until each surface is cut over.


## See also

- [ADR 0017: Internationalization Architecture](0017-text-ownership-localization-scope.md) — localization foundation
- [ADR 0002: Persistence Architecture](0002-persistence-architecture.md) — infrastructure patterns
