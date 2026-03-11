# Market Source Rate Limits

IRIS applies a shared rate-limit manager for market data and market cap lookups.

## Official limits

| Source | Policy used in IRIS | Source |
| --- | --- | --- |
| Binance Spot | `6000` request-weight per `60s`, kline request cost `2` | https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints and `GET /api/v3/exchangeInfo` |
| Coinbase Exchange public REST | `10` requests per `1s` per IP | https://docs.cdp.coinbase.com/exchange/introduction/rate-limits-overview |
| Polygon / Massive free | `5` requests per `60s` | official market pages such as https://polygon.io/currencies and https://polygon.io/indices |
| KuCoin public REST | `2000` quota per `30s`, kline request cost `3` | https://www.kucoin.com/docs-new/rate-limit and the Get Klines endpoint docs |
| Twelve Data Basic | `8` API credits per `60s` | https://twelvedata.com/pricing |
| Alpha Vantage free | `25` requests per day | https://www.alphavantage.co/support/ |
| CoinGecko Demo/Public | about `30` calls per minute | https://docs.coingecko.com/docs/common-errors-rate-limit |

## Conservative client-side caps

These two sources do not publish a stable public numeric limit for the endpoints IRIS uses, so IRIS applies a protective local cap and still honors provider throttling responses:

| Source | Policy used in IRIS | Note |
| --- | --- | --- |
| MOEX ISS | `0.5s` minimum interval | no published numeric public cap found in ISS docs |
| Yahoo Finance chart endpoint | `2.0s` minimum interval | endpoint is unofficial/publicly undocumented |
| Kraken public OHLC | `1.0s` minimum interval | published docs are centered on account/API-key counters, not the unauthenticated public path used here |
