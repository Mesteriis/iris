# ADR 0001: Event-Driven Runtime Architecture

## Status

**Accepted**

## Date

2025-01-15

## Context

IRIS performs complex analytical processing of market data:

- candle ingestion
- indicator computation
- pattern detection
- market-regime construction
- cross-market correlation
- signal generation
- signal fusion
- investment-decision generation
- portfolio management

A naive architecture would execute all of this through:

- cron jobs
- synchronous pipelines
- periodic batch computation

That approach scales poorly and recovers poorly after failures.

## Decision

IRIS uses an event-driven runtime pipeline.

**Pipeline:**

```text
candle_closed
  -> indicator_updated
  -> analysis_requested
  -> pattern_detected
  -> decision_generated
  -> portfolio_actions
```

Each stage is implemented as an independent worker.

Workers exchange events through Redis Streams.

## Consequences

### Positive

- subsystem independence
- better failure resilience
- horizontal-scaling potential
- straightforward event replay

### Negative

- higher runtime complexity
- stronger observability requirements

## See also

- [ADR 0003: Control Plane for Event Routing](0003-control-plane-event-routing.md) — dynamic event routing
- [ADR 0009: Signals Service/Engine Split](0009-signals-service-engine-split.md) — service orchestration
