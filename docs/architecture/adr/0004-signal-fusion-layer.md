# ADR 0004: Signal Fusion Layer

## Status

**Accepted**

## Date

2025-01-18

## Context

Market signals can contradict one another.

**For example:**

- a pattern says `BUY`
- the market regime says `HOLD`
- a cross-market signal says `SELL`

A signal-aggregation layer is required.

## Decision

IRIS introduces a Signal Fusion Engine.

**The fusion layer:**

- reads the latest signal groups
- weights them with contextual adjustments
- resolves conflicts
- generates a unified market decision

The result is stored in:

- `market_decisions`

## Consequences

### Positive

- one coherent market stance
- more stable decisions

### Negative

- fusion logic can become too complex
- explainability is required

## See also

- [ADR 0007: Cross-Market Intelligence](0007-cross-market-intelligence.md) — correlation analysis
- [ADR 0006: Portfolio Engine Separation](0006-portfolio-engine-separation.md) — execution of decisions
