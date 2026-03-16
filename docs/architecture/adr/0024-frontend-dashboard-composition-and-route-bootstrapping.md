# ADR 0024: Frontend Dashboard Composition and Route-Owned Bootstrapping

## Status

Accepted

## Date

2026-03-15

## Context

The frontend already has a working visual language and a reusable UI kit, but the screen composition does not yet respect clear architectural boundaries:

- route components such as `frontend/src/pages/Coins.vue` accumulated screen orchestration, derived view-model logic, mutation handlers, and large template trees in a single file;
- `App.vue` bootstrapped dashboard data globally, even when the active route did not need that data;
- the root layout component depended on unrelated modules and stale imports, which made the shell brittle and difficult to reuse;
- dashboard capabilities such as portfolio, cross-market analysis, research, operations, and coverage were rendered as one continuous implementation unit instead of distinct feature slices.

This violated the intent of the [Principal Engineering Checklist](../principal-engineering-checklist.md): architectural layering must not collapse, responsibilities must remain explicit, and composition boundaries must be obvious to reviewers.

## Decision

The frontend dashboard uses feature-oriented composition with route-owned bootstrapping.

### Route Entry Rules

- `App.vue` is a neutral application shell and does not bootstrap feature data;
- route entry files under `frontend/src/pages/` stay thin and primarily mount a feature screen;
- each route owns its own bootstrap lifecycle and loads only the state needed for that screen.

### Dashboard Composition Rules

- dashboard implementation lives under `frontend/src/features/dashboard/`;
- the feature screen composes domain sections such as overview, portfolio, cross-market, operations, research, and coverage;
- each section owns its own template and local interaction logic while reading shared data from the domain store;
- repeated presentation decisions such as decision-tone mapping live in feature-local helpers instead of being duplicated in every route file.

### UI Ownership Rules

- `frontend/src/ui/` remains the home of generic primitives;
- `frontend/src/components/layout/` owns neutral application shell concerns only;
- feature sections may reuse existing CSS tokens and visual primitives, but they do not redefine the design system;
- initial refactoring preserves the current visual style and information density unless a later ADR changes the dashboard information architecture intentionally.

### Store Boundary Rules

- shared stores remain responsible for fetching and caching dashboard data;
- feature sections may consume store selectors directly, but route files should not reimplement store shaping inline;
- application shell code may display already-available store state, but it must not trigger feature fetches itself.

## Consequences

### Positive

- route components become reviewable and stop acting as monoliths;
- dashboard concerns are grouped by business capability instead of by one large template file;
- the root application shell no longer couples unrelated routes to dashboard bootstrap cost;
- future dashboard changes can be made section-by-section without destabilizing the whole screen;
- the existing UI kit and visual language remain reusable without blocking architecture cleanup.

### Negative

- the frontend gains more files and section boundaries to navigate;
- some interactions now live in section-local components instead of one obvious page file;
- contributors must preserve the route-shell-feature-store split instead of adding new logic directly into route entrypoints.

## See also

- [Principal Engineering Checklist](../principal-engineering-checklist.md)
- [ADR 0019: Package Structure, Import Rules, and Source Root Policy](0019-package-structure-import-rules.md)
- [ADR 0020: Dependency Direction Rules and Import Boundaries](0020-dependency-direction-import-boundaries.md)
- [ADR 0023: Documentation Structure and Naming](0023-documentation-structure-and-naming.md)
