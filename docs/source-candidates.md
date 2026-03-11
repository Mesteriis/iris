# Additional Market Data Source Candidates

This shortlist is focused on gaps that still matter for IRIS: indices, FX, metals, and energy.

## Integrated candidate

### Polygon / Massive

- Index docs: https://polygon.io/docs/rest/indices/aggregates/custom-bars
- Forex docs: https://polygon.io/docs/rest/forex/aggregates/custom-bars
- Market pages: https://polygon.io/indices and https://polygon.io/currencies

Status in IRIS:
- Added as a runtime source for `index` and `forex`.
- Intended as the first exchange-grade replacement for Yahoo on U.S. macro indices.

Fit:
- Better match than TraderMade for canonical index candles.
- REST aggregate bars line up with IRIS candle model directly.

Caveat:
- Requires API key and the free tier is tight.
- The currently mapped set is intentionally narrow: U.S. indices and major FX pairs only.

## Candidate worth testing later

### TraderMade

- Docs: https://tradermade.com/docs/restful-api
- Free-tier note: https://tradermade.com/docs/restful-api/free-tier.pdf
- Coverage pages:
  - FX: https://tradermade.com/forex
  - CFDs: https://tradermade.com/cfds

Fit:
- Strong for FX.
- Also covers metals, energy, and indices via CFD-style instruments.

Why it is not wired into IRIS by default:
- For IRIS canonical history, this would mix proxy/CFD bars into the same layer as exchange-grade sources.
- It can still be useful later as an explicitly marked fallback layer.

## Candidates to avoid for IRIS primary candles

### EODHD

- Coverage page: https://eodhd.com/lp/historical-eod-api

Why it looks attractive:
- Broad coverage across stocks, ETFs, forex, and crypto.

Why it is a bad fit for canonical IRIS candles:
- Their own page states that CFDs and forex are not exchange data and may be indicative.
- For IRIS, where we explicitly avoid fake or synthetic trading bars, this is not a good primary source.

## Practical recommendation

If the next goal is to close the current gap quickly:

1. Add TraderMade as an optional fallback for `forex`, `metal`, and `energy`.
2. Keep it opt-in for `index`, because those would be CFD proxies.
3. For exchange-grade U.S. and European indices, evaluate Massive or another licensed index-focused provider instead of layering more unofficial endpoints.
