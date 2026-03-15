# ADR 0006: Portfolio Engine Separation

## Status

**Accepted**

## Date

2025-01-20

## Context

Analytical signals and real actions must be separated.

Analytics can be imperfect, but portfolio actions require strict rules.

## Decision

IRIS introduces a dedicated Portfolio Engine.

**The portfolio engine:**

- reads market decisions
- applies risk limits
- calculates position size
- generates portfolio actions

**Core constraints:**

- maximum position size
- maximum portfolio exposure
- risk adjustments

## Consequences

### Positive

- clear separation between analysis and action
- safer capital management

### Negative

- an additional architectural layer

## See also

- [ADR 0004: Signal Fusion Layer](0004-signal-fusion-layer.md) — signal source
- [ADR 0012: Services Return Domain Contracts](0012-services-return-domain-contracts.md) — service-layer patterns
