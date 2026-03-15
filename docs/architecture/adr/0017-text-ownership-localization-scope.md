# ADR 0017: Text Ownership Model and Localization Scope

## Status

Accepted

## Date

2026-01-15

## Context

IRIS is a single-user analytical system designed for local use. The system is not multi-tenant SaaS and does not require simultaneous operation in different languages.

The interface language is set by a single user in system settings and applies to the entire platform.

This means:

- The system operates in one language at a time
- Localization can be global
- No need to store locale at request or user level
- No need to maintain parallel localizations

However, the architecture must remain extensible to support new languages in the future without changing business logic.

## Decision

IRIS uses a Global Locale Model.

The system language is stored in global settings.

**Example:**

```python
settings.language = "ru"
```

The localization engine uses this locale for all user messages.

### Locale Resolution

The order of language determination:

1. **System Settings**: `settings.language`
2. **Default locale**: `en`

`Accept-Language` header is not used.

### Scope of Localization

Localization applies only to user-facing texts. This includes:

- UI
- API responses
- Dashboards
- Notifications
- Home Assistant UI
- Reports
- Documentation

### Non-Localized Layers

The following parts of the system are never translated:

**Domain Layer**

- Enums
- Domain states
- Event names
- Strategy identifiers

**Database**

- Stored values
- Enum values
- Identifiers

**Infrastructure**

- Logs
- Metrics
- Telemetry
- Tracing

**Integration Contracts**

- Event bus
- Home Assistant entities
- Service identifiers

### Text Ownership Model

To prevent chaos, a clear text ownership model is introduced.

**Domain Layer**

Domain does not own text. Domain returns:

- Codes
- Enums
- Structured data
- Parameters

**Example:**

```
DomainError(
    code="market_not_found",
    params={"market": "BTCUSDT"}
)
```

**Localization Layer**

The localization engine owns human text. It is responsible for:

- Translation
- Formatting
- Pluralization
- Parameter interpolation

**Transport Layer**

The transport layer connects domain and localization. It:

- Accepts message_key
- Calls localization engine
- Returns localized text

**Frontend**

The frontend rewrite is not started yet, so frontend localization is not the current source of truth.

The target frontend model must consume backend-owned `message_key` contracts and must not introduce a competing text taxonomy.

**Integrations**

Integrations use backend-owned business `message_key` contracts for runtime/business narration.

Static integration chrome, such as Home Assistant `strings.json` and `translations/*`, remains integration-owned.

### Message Flow

**Example of complete flow:**

1. **Domain Layer**

```
raise DomainError(
    code="market_not_found",
    params={"market": "BTCUSDT"}
)
```

2. **Transport Layer**

```
message_key = error.market_not_found
```

3. **Localization Layer**

```
translate(
    key="error.market_not_found",
    locale=settings.language,
    params={"market": "BTCUSDT"}
)
```

4. **Output**

```
"Market BTCUSDT not found"
```

### Catalog Structure

Translation catalogs:

```
core/i18n/catalogs/
  en.yaml
  ru.yaml
```

**Example:**

```yaml
error.market_not_found:
  message: "Market '{market}' not found"
```

### Catalog Governance

Each message_key must have:

- English version (canonical)
- Translations
- Description

**Example:**

```yaml
error.market_not_found:
  description: Market identifier does not exist
  message: "Market '{market}' not found"
```

### Translation Coverage

CI must check:

- No untranslated keys
- Parameter matching
- Catalog synchronization

### Logging Policy

Logs always remain in English. Localization in logs is prohibited.

This is necessary for:

- Debugging
- Incident analysis
- Observability

### Terminology Governance

IRIS maintains a unified terminology dictionary in `docs/architecture/terminology.md`.

It defines:

- Canonical domain terms
- Allowed translations
- Forbidden translations

**Example:**

```
draft → not translated
topology → translated as "topology"
```

### Future Evolution

If IRIS becomes a multi-user system, the architecture can be extended:

```
locale → user preference
locale resolution → request based
Accept-Language support
```

The current architecture allows this without changing domain logic.

## Consequences

### Positive

- Simple localization model
- No runtime complexity
- Clean domain architecture
- Unified system dictionary

### Negative

- Cannot use different languages simultaneously

This limitation is acceptable because IRIS is a single-user system.

## See also

- [ADR 0016: Error Taxonomy And Boundary Localization](0016-error-taxonomy-boundary-localization.md) — error handling
- [Home Assistant Overview](../../home-assistant/index.md) — Home Assistant integration
