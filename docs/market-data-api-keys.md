# Market Data API Keys

IRIS can boot without paid or external market-data credentials, but full seeded-asset coverage and live capability discovery depend on provider API keys.

Use this page as the operational source of truth for:

- which environment variable each provider uses;
- where the key is obtained;
- which official documentation explains the provider-side key flow;
- which sources currently do not require keys in IRIS.

## Active Credentialed Providers

| Environment variable | Provider | IRIS usage | Get API key | Official docs |
|---|---|---|---|---|
| `POLYGON_API_KEY` | Polygon | primary `forex` and `index` provider; live listing discovery when quota allows | <https://polygon.io/dashboard/keys> | <https://polygon.io/docs> |
| `TWELVE_DATA_API_KEY` | Twelve Data | primary `forex`, `index`, and `metal` provider; live listing discovery | <https://twelvedata.com/apikey> | <https://twelvedata.com/docs> |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage | resilience provider for `forex`, `energy`, and `rates` | <https://www.alphavantage.co/support/#api-key> | <https://www.alphavantage.co/documentation/> |
| `FRED_API_KEY` | FRED | daily resilience provider for `DXY`, `NDX`, `VIX`, and `TNX` | <https://fredaccount.stlouisfed.org/apikeys> | <https://fred.stlouisfed.org/docs/api/api_key.html> |
| `EIA_API_KEY` | EIA Open Data | daily resilience provider for `WTIUSD`, `BRENTUSD`, and `NATGASUSD` | <https://www.eia.gov/opendata/register.php> | <https://www.eia.gov/opendata/documentation.php> |

## Current Runtime Expectation

- `POLYGON_API_KEY`, `TWELVE_DATA_API_KEY`, and `ALPHA_VANTAGE_API_KEY` remain part of the default market-data stack.
- `FRED_API_KEY` is required for the current daily macro resilience path.
- `EIA_API_KEY` is required for the current daily energy resilience path.
- If `FRED_API_KEY` or `EIA_API_KEY` is missing, IRIS still runs, but seeded macro and energy assets lose their intended resilience tier and fall back to weaker paths.

## Provider Notes

### Polygon

- IRIS uses Polygon as a primary provider for `forex` and `index`.
- Free-tier quota can rate-limit live symbol discovery, so runtime capability snapshots may temporarily go `stale`.

### Twelve Data

- IRIS uses Twelve Data as a broad reference-data layer and fallback path.
- Listing coverage can be wider than minute-level quota allows; symbol presence in listing does not guarantee generous intraday quota.

### Alpha Vantage

- IRIS uses Alpha Vantage for broad FX derivation plus curated `energy` and `rates` aliases.
- Some functions are plan-gated on the provider side; IRIS treats unsupported endpoints as source-level incompatibility, not as internal failure.

### FRED

- IRIS uses FRED for daily macro resilience only.
- `DXY` is approximated through a broad-dollar FRED series rather than the exact ICE U.S. Dollar Index.

### EIA Open Data

- IRIS uses EIA for daily energy resilience only.
- EIA currently covers the seeded daily fallback path for `WTIUSD`, `BRENTUSD`, and `NATGASUSD`.

## Sources Without API Keys

The following adapters currently do not require API keys in IRIS:

- `binance`
- `coinbase`
- `kraken`
- `kucoin`
- `moex`
- `stooq`
- `yahoo`

These sources may still impose anonymous throttling, unofficial access limits, or anti-bot controls.

## Local Setup

Repository templates already expose all current market-data key slots:

- root template: `.env.example`
- backend template: `backend/.env.example`

For host-side backend development:

```bash
cd backend
cp .env.example .env
```

Then fill only the keys you actually use.
