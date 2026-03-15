# ADR 0023: Documentation Structure and Naming

## Status

Accepted

## Date

2026-03-15

## Context

The `docs/` tree accumulated multiple naming styles and path conventions:

- short acronyms such as `ha/` and `iso/` hid the actual scope of a section;
- some documents duplicated the parent scope in the filename, for example `ha-02-protocol-spec.md`;
- one architecture overview lived as `docs/architecture.md` while the rest of the section already lived under `docs/architecture/`;
- ADR filenames drifted between competing slugs, which made cross-links and navigation brittle;
- non-normative architecture notes were mixed together with ADRs.

This made repository navigation slower and left too much room for ambiguous or stale links.

## Decision

The documentation tree uses explicit scope names, stable path patterns, and section-local indexes.

### Top-Level Section Rules

- top-level documentation sections use full, descriptive names: `architecture`, `delivery`, `home-assistant`, `product`, `_generated`;
- section overviews live at `section/index.md`, not as sibling files like `section.md`;
- short acronyms in paths are avoided unless they are the canonical product name or standard term.

### File Naming Rules

- markdown filenames use lowercase kebab-case;
- filenames describe the document subject, not the folder plus a sequence number;
- parent-scope prefixes are not repeated in filenames when the folder already provides that context;
- operational document nouns stay explicit: `*-plan`, `*-audit`, `*-progress`, `*-checklist`, `*-specification`.

### ADR Rules

- ADRs live under `*/adr/`;
- global architecture ADRs use `docs/architecture/adr/<number>-<decision-slug>.md`;
- section-local ADRs use the same pattern within their own scope when the artifact is truly an ADR;
- every ADR section has its own `adr/index.md`.

### Note Rules

- non-normative explanatory documents live under `notes/`;
- notes use descriptive kebab-case filenames without ADR numbering;
- notes may summarize or visualize architecture, but they do not redefine normative decisions.

### Cross-Link Rules

- links between documentation pages use repository-relative paths within the same section when possible;
- overview pages must link to the local `index.md` or `adr/index.md` entrypoints, not only to leaf pages;
- when a document is normative for a scope, related plan/progress docs must link back to it near the top of the file.

## Consequences

### Positive

- documentation paths become readable without opening the file;
- section boundaries become obvious from the path alone;
- ADR navigation is predictable across architecture and integration scopes;
- stale links are easier to detect mechanically;
- future docs can be added without inventing a new naming pattern.

### Negative

- existing links, nav entries, and external references must be updated when the structure changes;
- older path references in branches, notes, or PRs may become outdated;
- contributors must follow the convention instead of inventing local shortcuts.

## Examples

- `docs/architecture/index.md`
- `docs/architecture/adr/0023-documentation-structure-and-naming.md`
- `docs/delivery/service-layer-refactor-audit.md`
- `docs/home-assistant/protocol-specification.md`
- `docs/home-assistant/notes/integration-architecture.md`

## See also

- [ADR 0019: Package Structure, Import Rules, and Source Root Policy](0019-package-structure-import-rules.md)
- [ADR 0020: Dependency Direction Rules and Import Boundaries](0020-dependency-direction-import-boundaries.md)
- [Home Assistant Notes](../../home-assistant/notes/index.md)
