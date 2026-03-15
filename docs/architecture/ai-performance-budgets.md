# AI Performance Budgets

## Status

Accepted on 2026-03-14 as the performance budget companion to ADR 0015.

## Sources

- `docs/architecture/adr/0015-ai-platform-layer.md`
- `docs/delivery/lazy-investor-ai-plan.md`
- `docs/architecture/service-layer-performance-budgets.md`

## Scope

This document defines the bounded performance and payload budgets for IRIS AI capabilities.

These budgets exist to keep AI execution useful without letting it destabilize deterministic runtime paths.

## Global Budgets

The following budgets are normative:

- AI provider request timeout defaults to a hard cap of 15 seconds unless an explicit per-provider override lowers it;
- heavy AI work must not run on shared analytical worker lanes;
- public or operator-facing read endpoints must not perform heavyweight synchronous generation;
- all expensive generation paths must be async, tracked or event-driven;
- persisted AI artifacts must carry execution metadata sufficient for latency, fallback and validation auditing.

## Payload Budgets

Current bounded human-facing payload budgets are:

| Capability | Bounded output |
| --- | --- |
| `notification_humanize` | title up to 96 chars, message up to 280 chars |
| `brief_generate` | title up to 120 chars, compact summary up to 640 chars, up to 5 bullets |
| `explain_generate` | title up to 120 chars, explanation up to 720 chars, up to 5 bullets |
| `hypothesis_generate` | structured JSON only; no unbounded prose payload |

These limits are part of the prompt and output-contract design, not only a UI concern.

## Execution Budgets by Capability

### `hypothesis_generate`

- execution remains isolated from deterministic `hypothesis_evaluation`;
- generation failures must not disable read or evaluation surfaces;
- fallback behavior is explicit and auditable, not silent.

### `notification_humanize`

- short context only;
- short bounded output only;
- degraded mode may use deterministic template humanization;
- execution stays on dedicated notification workers.

### `brief_generate`

- generation is async only;
- deterministic context bundles may use `json`, `compact_json`, `toon` or `csv` where justified;
- resulting artifact is stored and exposed through cached read surfaces with freshness metadata.

### `explain_generate`

- generation is async only;
- output must remain bounded and structured;
- degraded mode may use deterministic summary generation instead of pretending to be a real provider response.

## HTTP Surface Budgets

The current HTTP policy is:

- brief and explanation read surfaces are read paths, not hidden generation paths;
- generation triggers return tracked operations instead of blocking until provider completion;
- HA embedded profile may expose selected AI-derived reads but not the corresponding operator/admin or generation triggers;
- operator catalogs and admin routes live in control-plane, not in parallel AI-specific admin surfaces.

## Queue and Isolation Budgets

The following isolation rules are mandatory:

- AI generation work must never consume the shared analytical worker budget reserved for canonical domain computation;
- control-plane dispatching, deterministic schedulers and AI workers must remain independently observable;
- queue saturation in AI lanes must be visible through capability-specific telemetry and must not be hidden inside generic worker pools.

## Validation and Degraded Budgets

Validation is part of the performance budget because invalid output is wasted runtime.

IRIS therefore requires:

- schema-first validation after provider output;
- explicit `validation_status`;
- explicit degraded strategy names;
- no silent conversion of malformed provider output into persisted business artifacts.

## Definition of Compliance

IRIS AI performance is compliant with this budget only when:

- heavy AI execution stays isolated from deterministic analytical lanes;
- generation surfaces remain async or event-driven;
- bounded payload contracts are preserved;
- latency, fallback and validation metadata are emitted for every persisted AI artifact;
- read paths continue to expose freshness semantics instead of hiding synchronous AI work.
