# ADR 0028: Market Data Source Catalog and Support Tiers

## Status

Accepted

## Date

2026-03-16

## Context

IRIS now has three different layers of truth around market-data sourcing:

- observed assets live in PostgreSQL by [ADR 0026](0026-observed-asset-inventory-is-db-owned.md);
- runtime capability snapshots live in Redis by [ADR 0027](0027-live-market-source-capability-registry-in-redis.md);
- source adapters and provider precedence live in backend code.

What was still missing was one architectural source of truth for the provider catalog itself:

- which market-data providers are approved for IRIS at all;
- which asset classes each provider may serve;
- which providers are already implemented vs planned;
- which providers are only acceptable as approximation or daily-resilience layers;
- which providers are required when exact index-owner or exchange-owner data matters.

Without this catalog, the codebase drifts into local assumptions:

- a provider may be added in code without architectural approval;
- a seed asset may depend on a provider that is not durable enough for startup coverage;
- "default" source routing becomes implicit instead of governed.

## Decision

IRIS maintains one ADR-owned market-data provider catalog and support-tier model.

This ADR is the source of truth for which providers are allowed in the platform.

### Catalog Rules

- every provider used by `market_data` must appear in this ADR;
- every provider listed here must have one of three statuses:
  - `implemented`
  - `planned`
  - `licensed/escalation`
- every provider listed here must also declare its support tier:
  - `primary`
  - `resilience`
  - `exact`
- `coin.source` values in PostgreSQL may only reference provider ids cataloged here, or the synthetic routing value `default`;
- Redis capability snapshots are runtime state for a provider from this catalog, not the catalog itself.

### Tier Rules

- `primary` means normal production fetch path for the relevant asset class;
- `resilience` means fallback or daily-survival coverage that keeps seeded assets alive when primary providers fail or rate-limit;
- `exact` means owner-grade or licensed feeds required when public/free providers are only proxies or approximations.

### Startup Coverage Rule

- every enabled seed asset must have at least one non-experimental provider path from this catalog;
- macro and energy seed assets should have at least one resilience path independent from Yahoo-style unofficial scraping;
- if a seed asset is covered only by daily resilience providers, its seeded base candle must be `1d`, not intraday;
- if an asset can only be supported by approximation, that approximation must be documented explicitly in this ADR.

## Provider Catalog

### Implemented Primary Providers

| Provider ID | Status | Tier | Asset Classes | Notes |
|---|---|---|---|---|
| `binance` | implemented | primary | `crypto` | Spot crypto primary source. Live listing discovery supported. |
| `kucoin` | implemented | primary | `crypto` | Spot crypto primary source. Live listing discovery supported. |
| `kraken` | implemented | primary | `crypto` | Spot crypto primary source. Live listing discovery supported. |
| `coinbase` | implemented | primary | `crypto` | Spot crypto primary source. Live listing discovery supported. |
| `moex` | implemented | primary | `index` | Primary source for MOEX-native indices such as `IMOEX` and `RTSI`. |
| `polygon` | implemented | primary | `forex`, `index` | Official API product, but rate-limited in free usage. Live listing discovery supported when quota allows. |
| `twelvedata` | implemented | primary | `forex`, `index`, `metal` | Broad reference-data provider. Some symbols are plan-gated. Live listing discovery supported. |
| `yahoo` | implemented | primary | `crypto`, `forex`, `index`, `metal`, `energy` | Broad practical fallback, but unofficial and rate-limit prone. Alias validation only. |

### Implemented Resilience Providers

| Provider ID | Status | Tier | Asset Classes | Notes |
|---|---|---|---|---|
| `alphavantage` | implemented | resilience | `forex`, `energy`, `rates` | Official API. FX universe is derived from published currency list; energy and rates use validated curated aliases. |
| `eia` | implemented | resilience | `energy` | Official EIA Open Data daily fallback for `WTI`, `BRENT`, and `NATGASUSD`. |
| `fred` | implemented | resilience | `index`, `rates`, `macro` | Daily macro fallback via FRED series API. Suitable for `VIX`, `TNX`, `NDX`, and a broad-dollar proxy for `DXY`. |
| `stooq` | implemented | resilience | `index`, `metal` | Daily-only public fallback. Alias validation only. |

### Approved Licensed or Exact Providers

| Provider ID | Status | Tier | Asset Classes | Notes |
|---|---|---|---|---|
| `cboe_indices` | licensed/escalation | exact | `index`, `rates`, `volatility` | Exact owner-grade path for `VIX` and Cboe-owned rate indices such as `TNX`. |
| `nasdaq_gids` | licensed/escalation | exact | `index` | Exact owner-grade path for `NDX`. |
| `ice_data` | licensed/escalation | exact | `index`, `energy`, `macro` | Exact owner-grade path for ICE U.S. Dollar Index (`DXY`) and ICE-side energy benchmarks such as Brent. |
| `cme_market_data` | licensed/escalation | exact | `energy` | Exact owner-grade path for CME/NYMEX benchmarks such as WTI and Natural Gas. |
| `stoxx_licensed` | licensed/escalation | exact | `index` | Exact owner-grade path for `STOXX50E`. |
| `sp_dji_licensed` | licensed/escalation | exact | `index` | Exact owner-grade path for `DJI` and `GSPC` families when public proxies are not acceptable. |

## Asset-Coverage Guidance

### Assets With Strong Public Coverage

- `BTCUSD`, `ETHUSD`, `SOLUSD`, `DOGEUSD`, `ETHBTC`, `FETUSD`, `RENDERUSD`, `TAOUSD`, `AKTUSD`
- `EURUSD`, `USDRUB`, `USDCNY`
- `IMOEX`, `RTSI`
- `DJI`, `GSPC`, `GDAXI`, `STOXX50E`
- `XAUUSD`, `XAGUSD`

These assets may use public providers as their primary operational path.

### Assets Requiring Resilience Beyond Yahoo

- `DXY`
- `NDX`
- `VIX`
- `TNX`
- `NATGASUSD`
- `BRENTUSD`
- `WTIUSD`

These assets must not rely solely on Yahoo-style unofficial access if they remain in the seed set.

### Approximation Rules

- `DXY` may be approximated by FRED broad-dollar series only if the product requirement is "keep macro dollar regime alive" rather than "exact ICE U.S. Dollar Index".
- `TNX` may be approximated by FRED treasury yield series only if the product requirement is "daily 10Y yield level" rather than "exact Cboe TNX instrument".
- `VIX`, `NDX`, `DXY`, `BRENTUSD`, `WTIUSD`, and `NATGASUSD` should move to `exact` providers when exact branded benchmark identity becomes a hard requirement.

## Consequences

### Positive

- provider adoption is now governed explicitly instead of being inferred from code;
- DB asset inventory, Redis capability state, and provider catalog each have one clear owner;
- gaps in seed coverage become visible as architectural issues instead of runtime surprises.

### Negative

- this ADR must be kept current whenever a provider is added, removed, or re-tiered;
- some source ids represent licensed escalation paths that may never be implemented in local development environments;
- the catalog is intentionally broader than the current codebase, so code and ADR can temporarily differ while planned providers are being built.

## See also

- [ADR 0011: Analytical Engines Never Fetch External Data Directly](0011-analytical-engines-never-fetch.md)
- [ADR 0013: Async Classes for Orchestration, Pure Functions for Analysis](0013-async-classes-for-orchestration-pure-functions-for-analysis.md)
- [ADR 0025: Runtime Proxy Registry for Public Market Sources](0025-runtime-proxy-registry-for-public-market-sources.md)
- [ADR 0026: Observed Asset Inventory Is DB-Owned](0026-observed-asset-inventory-is-db-owned.md)
- [ADR 0027: Live Market-Source Capability Registry in Redis](0027-live-market-source-capability-registry-in-redis.md)
