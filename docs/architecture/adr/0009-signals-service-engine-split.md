# ADR 0009: Canonical `signals` Service/Engine Split

## Status

Accepted

## Context

`signals` was the reference hotspot for the service-layer refactor:

- the old `backend/src/apps/signals/services.py` mixed orchestration, analytical fusion logic, history evaluation, cross-domain data access and summary-oriented results;
- fusion and history logic were hard to test without runtime wiring;
- public service contracts leaked summary-shaped compatibility helpers instead of typed application results.

The service-layer standard for IRIS requires:

- orchestration services to own loading, persistence and post-commit side effects;
- analytical engines to stay pure and deterministic;
- explicit adapters for cross-domain data access;
- typed service results with no `to_summary()` compatibility layer.

## Decision

`signals` is split into a canonical final-form package layout:

- `src/apps/signals/services/` contains orchestration-only services and side-effect boundaries;
- `src/apps/signals/engines/` contains pure fusion/history analytical logic with typed inputs and explainability contracts;
- cross-domain market-data access is isolated behind `src/apps/signals/integrations/market_data.py`;
- public service results are dataclass contracts, not summary payload shapers.

## Consequences

This module now serves as the copyable reference for later hotspot rewrites.

The practical rules are:

- service tests cover wiring, invariants and post-commit behavior;
- engine tests cover deterministic analytical behavior without DB/runtime setup;
- future hotspot rewrites should copy this split directly instead of introducing interim compatibility wrappers.
