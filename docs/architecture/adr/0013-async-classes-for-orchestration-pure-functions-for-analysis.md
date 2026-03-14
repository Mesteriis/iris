# ADR 0013: Async Classes For Orchestration, Pure Functions For Analysis

## Status

Accepted

## Context

Two different kinds of code coexist in IRIS:

- orchestration code that coordinates repositories, units of work, adapters and side effects;
- analytical code that transforms already-loaded inputs into deterministic decisions or metrics.

Trying to force one object model onto both layers caused confusion:

- orchestration code became under-structured when written as free functions;
- analytical code became over-engineered when wrapped in async service objects only to perform pure math.

## Decision

IRIS uses async-class-first orchestration and pure-function-first analytical engines.

The practical rule is:

- orchestration services may be async classes with injected repositories/adapters and explicit lifecycle boundaries;
- analytical engines should default to pure functions and typed contracts;
- stateful or async engines require an explicit justification, not convenience;
- service modules should not absorb analytical helpers that belong in an engine package.

## Consequences

This preserves the right abstraction at each layer:

- orchestration stays explicit about dependencies and write boundaries;
- analytical behavior stays easy to test and reason about;
- the codebase avoids “everything is a service class” and “everything is a loose helper” extremes;
- the canonical `signals` split remains the reference pattern for later domains.
