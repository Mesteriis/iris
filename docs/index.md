# IRIS Documentation

IRIS is an event-driven market intelligence platform built around one canonical market-data store plus deterministic analytics, governed HTTP/API surfaces, portfolio automation, and optional AI-assisted reasoning.

This documentation set is organized around the current repository structure rather than legacy wiki layouts.

## Start Here

- [Getting Started](getting-started.md)
- [Architecture Overview](architecture.md)
- [ADR Index](architecture/adr/index.md)
- [Open Source Guide](open-source.md)

## Documentation Map

| Class | Location | Role |
|---|---|---|
| Architecture and governance | `docs/architecture/` | Accepted architecture decisions, policy docs, engineering guardrails |
| Execution plans and audits | `docs/iso/` | Working plans, refactor progress, implementation audits |
| Product notes | `docs/product/` | Product framing and review checklists |
| Home Assistant integration | `docs/ha/` | Protocol, integration architecture, backend and HACS plans |
| Generated artifacts | `docs/_generated/` | Code-derived HTTP capability and availability snapshots |
| Review snapshots | `docs/reviews/` | Time-bound reviews that may lag the live codebase |

## Current Sources Of Truth

When documents disagree, prefer them in this order:

1. Generated artifacts in `docs/_generated/`
2. Accepted ADRs and policy docs in `docs/architecture/`
3. Current rollout docs in `docs/iso/`
4. Historical reviews in `docs/reviews/`

## Main Topics

- [Architecture](architecture.md): runtime model, domains, control plane, persistence rules
- [Delivery And Audits](iso/index.md): implementation plans and refactor tracking
- [Home Assistant](ha/index.md): bridge protocol and integration design
- [Generated Governance Artifacts](_generated/index.md): HTTP contract inventory exported from code
- [Open Source](open-source.md): contribution, security, licensing, and repository expectations

## Repository Scope

The live backend currently includes:

- `market_data`
- `indicators`
- `patterns`
- `signals`
- `predictions`
- `cross_market`
- `portfolio`
- `anomalies`
- `news`
- `market_structure`
- `control_plane`
- `hypothesis_engine`
- `system`

The repository also includes:

- a Vue 3 frontend dashboard
- Home Assistant addon and custom-integration planning documents
- CI-enforced HTTP and service-layer governance artifacts
