# ADR 0007: Cross-Market Intelligence

## Status

**Accepted**

## Date

2025-01-21

## Context

The crypto market is highly interconnected.

**Examples:**

- BTC -> ETH
- ETH -> altcoins
- sector rotation

Ignoring these relationships weakens signals.

## Decision

IRIS introduces a Cross-Market Intelligence Layer.

**The system:**

- computes correlations
- identifies market leaders
- records lag relationships between assets
- strengthens follower-asset signals

Data is stored in:

- `coin_relations`

## Consequences

### Positive

- more contextual signals
- better identification of leader assets

### Negative

- more complex computation
- correct calibration is required

## See also

- [ADR 0004: Signal Fusion Layer](0004-signal-fusion-layer.md) — fusion with other signal sources
