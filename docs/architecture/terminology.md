# IRIS Terminology

This document is the canonical terminology reference used by ADR 0017.

## Purpose

The glossary exists to keep backend, frontend, docs, and integrations aligned on the same domain language.

It defines:

- canonical English source terms
- which terms may be localized in user-facing text
- which terms should remain in English
- discouraged variants that introduce ambiguity

## Rules

- Domain identifiers, event names, enum values, and protocol keys stay in English.
- UI and documentation may localize user-facing explanations, but they must preserve the canonical term mapping below.
- When a term is marked “keep in English,” localized prose may explain it, but the term itself should remain unchanged.

## Core Terms

| Canonical term | Localization policy | Notes |
|---|---|---|
| asset | may be localized | Use for user-facing portfolio and market context. |
| candle | may be localized | Time-series market candle. |
| signal | may be localized | Analytical signal, not a notification signal by default. |
| decision | may be localized | User-facing explanations may clarify the investment context when needed. |
| portfolio | may be localized | |
| prediction | may be localized | |
| anomaly | may be localized | |
| control plane | keep in English | Architectural term; it may be explained in localized prose. |
| event bus | keep in English | Avoid inventing transport-specific synonyms. |
| topology | keep in English | Matches ADR examples and UI/domain wording. |
| draft | keep in English | Avoid conflicting workflow translations. |
| runtime | keep in English | Keep stable across architecture and operations docs. |
| service | keep in English | Use as a technical-layer term. |
| engine | keep in English | Distinguishes analytical engine from service layer. |
| bridge | keep in English | Used for the Home Assistant integration boundary. |
| catalog | may be localized | For entity, command, and dashboard catalog. |
| dashboard | keep in English | Product and UI term kept as-is. |
| operation | may be localized | For tracked async operation lifecycle. |
| message key | keep in English | Refers to the localization-contract identifier. |

## Discouraged Variants

| Discouraged variant | Use instead | Reason |
|---|---|---|
| route schema | topology | Too narrow and conflicts with graph terminology. |
| workflow draft synonym | draft | Causes ambiguity across docs and UI. |
| alternative runtime spelling | runtime | Keep one spelling across architecture docs. |
| mixed service-engine term | engine or service | Mixed terms blur the service/engine split. |
| request locale | settings language | Request-scoped locale is out of scope for the current architecture. |

## Related Documents

- [ADR 0017: Text Ownership Model and Localization Scope](adr/0017-text-ownership-localization-scope.md)
- [ADR 0018: Message Key Taxonomy and Localization Naming Rules](adr/0018-message-key-taxonomy-naming.md)
- [Home Assistant Protocol Specification](../home-assistant/protocol-specification.md)
