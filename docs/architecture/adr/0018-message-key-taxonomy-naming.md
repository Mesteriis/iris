# ADR 0018: Message Key Taxonomy and Localization Naming Rules

## Status

Accepted

## Date

2026-01-20

## Context

IRIS implements a centralized multilingual architecture where:

- Internal system logic remains in English
- All user-facing text goes through the localization layer
- Localization is built on message_key + params
- The system is single-user
- Active language is set globally in settings

With this approach, message keys become the primary contract of the text system.

If message keys are not standardized upfront, problems arise over time:

- Duplicate keys
- Different naming styles
- Mix of technical and user-facing messages
- Loss of predictability
- Difficulty finding translations
- Growth of "dead" or orphan keys
- Chaos between backend, frontend, Home Assistant integration, and documentation

Therefore, a unified taxonomy and naming model for all localization keys is required.

## Decision

IRIS uses a hierarchical taxonomy for message keys.

Each key must:

- Be stable
- Be readable
- Reflect usage context
- Not depend on specific text wording
- Not contain localized text
- Not reflect UI layout or transport-specific details

A message key is a semantic identifier of meaning, not a text string.

### Canonical Structure

**Key format:**

```
domain.category.name
```

or

```
domain.subdomain.category.name
```

**Examples:**

```
error.market.not_found
error.strategy.invalid_state
ui.settings.locale.label
ui.settings.locale.description
notification.signal.detected
brief.strategy.created
report.market.summary_title
ha.entity.market_status.name
ha.entity.market_status.description
```

### Top-Level Namespaces

IRIS allows the following top-level namespaces:

- error
- ui
- notification
- brief
- report
- ha
- doc
- system

### Namespace Meanings

**error**

User-facing errors and error explanations.

**Examples:**

```
error.market.not_found
error.strategy.invalid_state
error.integration.timeout
```

**ui**

Static interface texts.

**Examples:**

```
ui.settings.title
ui.settings.locale.label
ui.dashboard.empty_state.title
```

**notification**

Notifications, alerts, messages, emitted user-facing events.

**Examples:**

```
notification.signal.detected
notification.system.sync_completed
```

**brief**

Texts related to brief generation, summaries, narrative outputs.

**Examples:**

```
brief.strategy.summary
brief.portfolio.performance
```

**report**

Texts in generated reports.

**Examples:**

```
report.market.summary_title
report.portfolio.positions
```

**ha**

Home Assistant-specific texts (entity names, etc.).

**Examples:**

```
ha.entity.market_status.name
ha.entity.market_status.description
```

**doc**

Documentation texts.

**Examples:**

```
doc.getting_started.guide.title
doc.api.endpoints.description
```

**system**

System messages (logs remain in English).

**Examples:**

```
system.startup.complete
system.backup.in_progress
```

### Naming Rules

1. **Use dots for hierarchy**: `domain.category.name`

2. **Use lowercase**: `error.market.not_found`

3. **Use snake_case for multi-word names**: `error.strategy.invalid_state`

4. **Be specific**: `error.market.not_found` not `error.not_found`

5. **Group related messages**: `ui.settings.*`, `ui.dashboard.*`

6. **Avoid abbreviations**: Use `description` not `desc`

7. **Use singular**: `notification.signal` not `notification.signals`

8. **Include context**: `error.market.not_found` not `error.not_found`

### Key Examples

**Error messages:**

```
error.market.not_found
error.market.invalid_symbol
error.strategy.invalid_state
error.strategy.max_position_exceeded
error.integration.ha_connection_failed
error.portfolio.insufficient_balance
```

**UI labels:**

```
ui.settings.title
ui.settings.locale.label
ui.settings.locale.description
ui.dashboard.overview.title
ui.dashboard.assets.empty_state
ui.button.save
ui.button.cancel
```

**Notifications:**

```
notification.signal.detected
notification.signal.confirmed
notification.system.backup_complete
notification.portfolio.rebalance_required
```

**Briefs:**

```
brief.strategy.summary
brief.portfolio.daily_summary
brief.market.analysis
```

**Reports:**

```
report.title.portfolio
report.column.asset
report.column.position
report.column.value
```

**Home Assistant:**

```
ha.entity.system_connection.name
ha.entity.system_connection.description
ha.entity.portfolio_value.name
ha.action.sync_portfolio.name
```

**Documentation:**

```
doc.getting_started.title
doc.api.authentication.description
doc.troubleshooting.connection_errors
```

### Anti-Patterns to Avoid

1. **Not using dots**: `errorMarketNotFound` → use `error.market.not_found`

2. **Using camelCase**: `errorMarketNotFound` → use `error.market.not_found`

3. **Including text**: `error.market.not_found_in_system` → use `error.market.not_found`

4. **Being too generic**: `error.not_found` → use `error.market.not_found`

5. **Using plural**: `notification.signals` → use `notification.signal`

6. **Hardcoding UI hints**: `ui.button_save` → use `ui.button.save`

### Validation Rules

CI must enforce:

- All keys use lowercase
- All keys use dots for hierarchy
- No duplicate keys exist
- All keys have English message in catalog
- All keys match taxonomy structure

### Migration Strategy

Existing keys should be migrated to the new taxonomy:

1. Audit existing keys
2. Map to new taxonomy
3. Add new keys alongside old
4. Update consumers to use new keys
5. Remove old keys after migration period

## Consequences

### Positive

- Unified text system across all layers
- Easy to find and manage translations
- Clear ownership of text
- Predictable key structure
- Easy to add new languages
- Clear separation of concerns

### Negative

- Requires migration of existing keys
- Initial investment in setting up taxonomy
- Requires discipline to maintain

## See also

- [ADR 0017: Text Ownership Model and Localization Scope](0017-text-ownership-localization-scope.md) — localization foundation
- [ADR 0016: Error Taxonomy And Boundary Localization](0016-error-taxonomy-boundary-localization.md) — error handling
