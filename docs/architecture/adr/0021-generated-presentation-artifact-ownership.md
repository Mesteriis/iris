# ADR 0021: Generated Presentation Artifact Ownership

## Status

Accepted

## Date

2026-03-16

## Context

ADR 0017 defines that localization belongs only to the presentation layer.

ADR 0018 defines the naming and taxonomy rules for `message_key`.

However, those ADRs do not fully define how persisted user-facing artifacts should be stored when the platform produces two different content classes:

1. Deterministic presentation content that can be represented as `message_key + params`
2. Non-deterministic AI-generated narrative text that does not have a stable message key

Without an explicit ownership model, the storage layer drifts into a hybrid design:

- locale becomes part of row identity
- rendered text becomes accidental source of truth
- deterministic and AI-generated artifacts follow different undocumented rules
- locale changes require duplicate rows or regeneration decisions that are not governed centrally

This gap affects persisted `notifications`, `explanations`, and `briefs`.

## Decision

Persisted user-facing artifacts use a single canonical presentation envelope.

### One Row Per Business Entity

Locale is not part of storage identity.

Examples:

- `ai_notifications` are unique by `source_event_type + source_event_id`
- `ai_explanations` are unique by `explain_kind + subject_id`

### Content Kinds

Each persisted presentation artifact declares `content_kind`.

Allowed values:

- `descriptor_bundle`
- `generated_text`

### Descriptor Bundle

`descriptor_bundle` is used when the artifact can be rendered deterministically from shared catalogs.

It stores:

- version
- kind
- field descriptors

Example:

```json
{
  "version": 1,
  "kind": "descriptor_bundle",
  "title": {"key": "notification.signal.created.title", "params": {"symbol": "BTCUSDT"}},
  "message": {"key": "notification.signal.created.message", "params": {"symbol": "BTCUSDT", "timeframe": 15}}
}
```

The localization engine renders these fields only on presentation boundaries.

### Generated Text

`generated_text` is used when the artifact is freeform AI output and does not have a stable message key contract.

It stores:

- version
- kind
- rendered locale
- rendered text fields

Example:

```json
{
  "version": 1,
  "kind": "generated_text",
  "rendered_locale": "en",
  "title": "ETHUSDT: anomaly detected",
  "message": "IRIS flagged a volatility anomaly for ETHUSDT."
}
```

Generated text is a presentation snapshot, not a domain fact.

### Legacy Text Columns

Legacy text columns may remain physically in the schema during migration, but they are not the source of truth.

Canonical content lives in the presentation envelope.

### Locale Changes

For `descriptor_bundle`, locale switching re-renders from catalogs and does not create a second row.

For `generated_text`, locale switching does not create a second row automatically.

If a different locale snapshot is needed, it must be produced by explicit regeneration or replacement of the same artifact row.

## Consequences

Positive:

- storage identity stays language-agnostic
- deterministic localized content remains fully centralized
- freeform AI narrative gets an explicit, governed ownership model
- locale changes stop multiplying rows

Tradeoffs:

- generated text remains locale-specific snapshot content
- migrations that collapse historic locale duplicates are lossy by design
- callers must understand `content_kind` instead of assuming every artifact is message-key-backed

## Follow-up

- add CI checks for content envelope validity and `content_kind` coverage

## See also

- [ADR 0017: Text Ownership Model and Localization Scope](0017-text-ownership-localization-scope.md)
- [ADR 0018: Message Key Taxonomy and Localization Naming Rules](0018-message-key-taxonomy-naming.md)
