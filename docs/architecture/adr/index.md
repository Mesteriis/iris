# Architecture Decision Records (ADR)

Collection of ADRs describing the key architectural decisions behind IRIS.

All ADRs follow the [MADR](https://adr.github.io/madr/) format:

- **Title**: `ADR-NUMBER: Title`
- **Status**: `Proposed | Accepted | Deprecated | Superseded`
- **Date**: `YYYY-MM-DD`
- **Context**: the problem or situation that requires a decision
- **Decision**: the chosen decision
- **Consequences**: positive and negative consequences
- **See also**: related ADRs

Starting with ADR 0023, files and paths follow one naming rule: `adr/<number>-<decision-slug>.md`.

## Contents

| # | ADR | Status | Date |
|---|-----|--------|------|
| 0001 | [Event-Driven Runtime](0001-event-driven-runtime.md) | Accepted | 2025-01-15 |
| 0002 | [Persistence Architecture](0002-persistence-architecture.md) | Accepted | 2025-01-16 |
| 0003 | [Control Plane for Event Routing](0003-control-plane-event-routing.md) | Accepted | 2025-01-17 |
| 0004 | [Signal Fusion Layer](0004-signal-fusion-layer.md) | Accepted | 2025-01-18 |
| 0005 | [Analytical Snapshot API Semantics](0005-analytical-snapshot-api-semantics.md) | Accepted | 2025-01-19 |
| 0006 | [Portfolio Engine Separation](0006-portfolio-engine-separation.md) | Accepted | 2025-01-20 |
| 0007 | [Cross-Market Intelligence](0007-cross-market-intelligence.md) | Accepted | 2025-01-21 |
| 0008 | [Research vs Production Runtime](0008-research-vs-production-runtime.md) | Accepted | 2025-01-22 |
| 0009 | [Signals Service/Engine Split](0009-signals-service-engine-split.md) | Accepted | 2025-02-01 |
| 0010 | [Caller Owns Commit Boundary](0010-caller-owns-commit-boundary.md) | Accepted | 2025-02-02 |
| 0011 | [Analytical Engines Never Fetch](0011-analytical-engines-never-fetch.md) | Accepted | 2025-02-03 |
| 0012 | [Services Return Domain Contracts](0012-services-return-domain-contracts.md) | Accepted | 2025-02-04 |
| 0013 | [Async Classes for Orchestration, Pure Functions for Analysis](0013-async-classes-for-orchestration-pure-functions-for-analysis.md) | Accepted | 2025-02-05 |
| 0014 | [Post-Commit Side Effects Only](0014-post-commit-side-effects-only.md) | Accepted | 2025-02-06 |
| 0015 | [AI Platform Layer](0015-ai-platform-layer.md) | Accepted | 2025-03-01 |
| 0016 | [Error Taxonomy Boundary Localization](0016-error-taxonomy-boundary-localization.md) | Proposed | 2025-03-10 |
| 0017 | [Text Ownership Localization Scope](0017-text-ownership-localization-scope.md) | Accepted | 2026-01-15 |
| 0018 | [Message Key Taxonomy Naming](0018-message-key-taxonomy-naming.md) | Accepted | 2026-01-20 |
| 0019 | [Package Structure Import Rules](0019-package-structure-import-rules.md) | Proposed | 2026-02-01 |
| 0020 | [Dependency Direction Import Boundaries](0020-dependency-direction-import-boundaries.md) | Proposed | 2026-02-10 |
| 0021 | [Generated Presentation Artifact Ownership](0021-generated-presentation-artifact-ownership.md) | Proposed | 2026-03-15 |
| 0022 | [Platform Maturity Additions](0022-platform-maturity-additions.md) | Accepted | 2026-03-01 |
| 0023 | [Documentation Structure and Naming](0023-documentation-structure-and-naming.md) | Accepted | 2026-03-15 |

## Related Documents

- [Service Layer Runtime Policies](../service-layer-runtime-policies.md)
- [Service Layer Performance Budgets](../service-layer-performance-budgets.md)
- [AI Runtime Policies](../ai-runtime-policies.md)
- [AI Performance Budgets](../ai-performance-budgets.md)
- [Complexity Guardrails](../complexity-guardrails.md)
- [Principal Engineering Checklist](../principal-engineering-checklist.md)
- [Architecture Notes](../notes/index.md)
- [Home Assistant Notes](../../home-assistant/notes/index.md)
- [Home Assistant Overview](../../home-assistant/index.md)
