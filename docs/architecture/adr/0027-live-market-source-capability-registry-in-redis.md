# ADR 0027: Live Market-Source Capability Registry in Redis

## Status

Accepted

## Date

2026-03-16

## Context

IRIS needs to know two different things about market-data providers:

- which symbols a provider currently exposes upstream;
- how a provider-specific symbol maps to IRIS canonical symbols when the transport naming differs from the common name.

Static Python files are not sufficient for this:

- provider universes change over time without code changes;
- some providers expose large listing endpoints that should be discovered live;
- some providers use transport-specific symbols such as `BTC-USDT`, `XXBTZUSD`, `I:SPX`, or `^DJI`.

At the same time, the observed asset inventory remains DB-owned by [ADR 0026](0026-observed-asset-inventory-is-db-owned.md). Provider capability discovery must not become a second asset inventory.

## Decision

IRIS maintains a live market-source capability registry in Redis.

### Registry Rules

- the registry stores provider capability snapshots, not observed assets;
- each snapshot contains provider-native symbols plus canonical alias mappings where IRIS can normalize them safely;
- Redis is the operational store for the registry because capability discovery is runtime infrastructure, not domain data.

### Refresh Rules

- the registry is loaded on service startup so source adapters can use the latest known mappings;
- discovery is triggered on startup and refreshed every hour through a scheduled runtime task;
- refresh uses upstream provider listing endpoints when they exist, and provider-specific alias validation when bulk listing is not available.

### Adapter Rules

- source adapters may keep small curated alias hints for normalization;
- adapters should first consult the live registry and fall back to curated hints when no live mapping is available;
- curated hints are transport adapters, not the source of truth for provider universe size.

## Consequences

### Positive

- symbol capability follows real upstream provider state more closely;
- source adapters can normalize provider-specific symbols without central hardcoded asset inventory files;
- runtime refresh is decoupled from PostgreSQL and remains internal infrastructure.

### Negative

- startup and hourly refresh now depend on extra upstream discovery calls;
- some providers still do not expose a true bulk universe endpoint, so discovery remains partial or validated-by-alias for them;
- Redis becomes the operational handoff for source capability state across processes.

## See also

- [ADR 0011: Analytical Engines Never Fetch External Data Directly](0011-analytical-engines-never-fetch.md)
- [ADR 0013: Async Classes for Orchestration, Pure Functions for Analysis](0013-async-classes-for-orchestration-pure-functions-for-analysis.md)
- [ADR 0026: Observed Asset Inventory Is DB-Owned](0026-observed-asset-inventory-is-db-owned.md)
- [ADR 0028: Market Data Source Catalog and Support Tiers](0028-market-data-source-catalog-and-support-tiers.md)
