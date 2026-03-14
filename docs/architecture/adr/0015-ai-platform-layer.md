# ADR 0015: Shared AI Platform Layer

## Status

Accepted

## Context

IRIS already adopted a service/engine split, runtime policies, analytical snapshot semantics and control-plane governed routing.

The existing `hypothesis_engine` proved that AI-assisted product flows are useful, but it also exposed architectural debt:

- AI provider adapters lived inside a single app instead of a shared platform layer;
- prompt vars could leak into infra routing decisions;
- `enable_hypothesis_engine` acted as a coarse runtime switch across HTTP, workers and scheduler registration;
- heuristic fallback blurred the boundary between real provider execution and degraded behavior;
- generation and deterministic evaluation were coupled too loosely.

The lazy-investor AI plan requires AI to become a governed platform capability, not an app-specific exception.

## Decision

IRIS introduces a shared `src/core/ai` platform layer and migrates hypothesis generation onto it.

The practical rules are:

- real provider adapters live in `core.ai.providers`, not inside domain services;
- provider availability is resolved through a typed provider registry and capability policy, not through a single feature flag;
- prompts may carry semantic defaults and style hints, but may not control provider routing, endpoints or auth;
- AI execution runs through a shared executor that resolves language, serializes context, validates structured output and emits execution metadata;
- heuristic logic is treated as an explicit degraded strategy, not as a peer provider;
- `hypothesis_generate` remains an AI capability, while `hypothesis_evaluation` stays a deterministic lifecycle path with independent runtime exposure.

## Consequences

This keeps AI aligned with the existing architecture family:

- read and evaluation surfaces remain observable even when no real provider is configured;
- generation worker registration becomes capability-aware and profile-aware;
- provider outages and degraded execution become auditable through explicit execution metadata instead of silent fallback;
- future capabilities such as `notification_humanize`, `brief_generate` and `explain_generate` can reuse the same runtime and governance model;
- the codebase avoids creating a parallel AI-specific architecture outside `core`, `apps` and `runtime`.
