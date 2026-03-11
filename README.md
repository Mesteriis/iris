# IRIS

IRIS is a market intelligence service built on top of the existing `coins`, `candles`, `indicator_cache`, `coin_metrics` and `signals` schema. The system keeps one canonical candle store and layers analytics, pattern intelligence and market structure on top of it.

## Stack

- FastAPI backend with SQLAlchemy, Alembic and embedded TaskIQ runtime
- Vue 3 dashboard with Pinia, Tailwind, Vite and ECharts
- PostgreSQL / TimescaleDB candle storage
- Home Assistant addon scaffold
- Home Assistant custom integration scaffold

## Run

```bash
docker compose up --build
```

Services:

- Backend: http://localhost:8000
- Frontend: http://localhost:3000

## Core data model

IRIS uses the existing schema instead of duplicating market history:

- `candles`
  Stores OHLCV. Primary key: `coin_id`, `timeframe`, `timestamp`.
- `indicator_cache`
  Stores computed indicators per coin, timeframe and timestamp.
- `coin_metrics`
  Stores current aggregate market state per coin. `market_regime` now holds the canonical regime used by the UI and contextual scoring.
- `signals`
  Stores classic analytics signals, pattern signals, cluster signals and hierarchy signals.
- `pattern_features`
  Feature flags for `pattern_detection`, `pattern_clusters`, `pattern_hierarchy`, `market_regime_engine`, `pattern_discovery_engine`.
- `pattern_registry`
  Pattern lifecycle registry with `ACTIVE`, `EXPERIMENTAL`, `COOLDOWN`, `DISABLED`.
- `pattern_statistics`
  Pattern performance snapshots with `sample_size`, `success_rate`, `avg_return`, `avg_drawdown`, `temperature`.
- `discovered_patterns`
  Review-only candidates from the discovery engine.
- `sectors`
  Sector taxonomy mapped from the existing `coins.theme`.
- `sector_metrics`
  Sector strength, relative strength, capital flow and volatility.
- `market_cycles`
  Latest cycle phase per coin and timeframe.

## Pattern Intelligence System

The pattern subsystem lives under `backend/app/patterns` and is integrated into the current analytics flow.

### Modules

- `engine.py`
  Incremental detection and bootstrap scanning.
- `registry.py`
  Pattern catalog sync and feature/lifecycle filtering.
- `lifecycle.py`
  Lifecycle state resolution from temperature.
- `statistics.py`
  Nightly pattern statistics refresh and temperature decay.
- `clusters.py`
  Cluster construction such as `pattern_cluster_bullish`.
- `hierarchy.py`
  Higher-order structures such as accumulation, distribution and trend exhaustion.
- `regime.py`
  Market regime detection per timeframe.
- `context.py`
  Contextual Signal Engine for `priority_score`, `context_score` and `regime_alignment`.
- `narrative.py`
  Sector strength, capital flow and rotation summary.
- `cycle.py`
  Market Cycle Engine.
- `discovery.py`
  Shape clustering and discovery candidate generation.

### Detector families

Implemented detector set:

- Structural:
  `head_shoulders`, `inverse_head_shoulders`, `double_top`, `double_bottom`, `triple_top`, `triple_bottom`, `ascending_triangle`, `descending_triangle`, `symmetrical_triangle`, `rising_wedge`, `falling_wedge`
- Continuation:
  `bull_flag`, `bear_flag`, `pennant`, `cup_and_handle`, `breakout_retest`, `consolidation_breakout`
- Momentum:
  `rsi_divergence`, `macd_cross`, `macd_divergence`, `momentum_exhaustion`
- Volatility:
  `bollinger_squeeze`, `bollinger_expansion`, `atr_spike`
- Volume:
  `volume_spike`, `volume_climax`, `volume_divergence`

Signals use `signal_type` values such as:

- `pattern_head_shoulders`
- `pattern_bull_flag`
- `pattern_volume_spike`
- `pattern_cluster_bullish`
- `pattern_hierarchy_accumulation`

## Runtime flow

### Incremental path

1. New closed candle is written into `candles`.
2. Existing analytics pipeline updates indicators and `coin_metrics`.
3. Pattern engine loads the last 200 candles and runs enabled detectors.
4. Cluster and hierarchy engines derive stronger structures from emitted pattern signals.
5. Regime and cycle context are applied.
6. Contextual Signal Engine updates:
   `priority_score = confidence * temperature * regime_alignment * volatility_alignment * liquidity_score * sector_alignment * cycle_alignment * cluster_bonus`

### Bootstrap path

- After historical coin backfill finishes, `patterns_bootstrap_scan` runs once for that coin and scans retained history.
- Historical detections are written into `signals`.
- `coins.history_backfill_completed_at` is updated when bootstrap completes.

### Scheduled TaskIQ jobs

All background work stays inside the existing backend runtime. No new worker container is introduced.

- `patterns_bootstrap_scan`
  One-time historical pattern bootstrap.
- `update_pattern_statistics`
  Nightly refresh of pattern statistics and lifecycle state transitions.
- `refresh_market_structure`
  Periodic sector metrics and market cycle refresh.
- `run_pattern_discovery`
  Periodic discovery candidate refresh.
- `signal_context_enrichment`
  Recomputes signal context on demand.

## Market structure layers

### Market Regime Engine

Regimes:

- `bull_trend`
- `bear_trend`
- `sideways_range`
- `high_volatility`
- `low_volatility`

The backend stores the canonical regime in `coin_metrics.market_regime` and exposes per-timeframe regime snapshots through the API.

### Market Narrative Engine

The sector layer reuses the current `theme` taxonomy by mapping it into `sectors` and `coins.sector_id`. `sector_metrics` tracks:

- `sector_strength`
- `relative_strength`
- `capital_flow`
- `volatility`

Narratives expose BTC dominance bias and sector leadership state for the dashboard.

### Market Cycle Engine

Phases:

- `ACCUMULATION`
- `EARLY_MARKUP`
- `MARKUP`
- `LATE_MARKUP`
- `DISTRIBUTION`
- `EARLY_MARKDOWN`
- `MARKDOWN`
- `CAPITULATION`

Cycle state is stored in `market_cycles` and fed back into contextual signal ranking.

### Pattern Discovery Engine

The discovery job clusters rolling price windows by normalized shape and volatility hash and writes candidates to `discovered_patterns`. These rows are never auto-enabled.

## API

Primary endpoints:

- `GET /signals`
- `GET /signals/top`
- `GET /patterns`
- `GET /coins/{symbol}/patterns`
- `GET /coins/{symbol}/regime`
- `GET /sectors`
- `GET /sectors/metrics`
- `GET /market/cycle`

The frontend uses these endpoints to show:

- active patterns
- priority-ranked signals
- cluster membership
- market regime
- cycle phase
- sector rotation
- pattern history

## Performance notes

- Candle history is never duplicated.
- Incremental detection reads the last 200 candles from `candles` / aggregate views.
- `ix_candles_coin_tf_ts_desc` accelerates the last-200-candle query pattern.
- Runtime scans full retained history only during bootstrap or scheduled discovery/statistics jobs, not during normal incremental operation.

## Notes

- TaskIQ workers run inside the backend service lifecycle. There is no separate worker container.
- The backend applies Alembic migrations during startup.
- On startup, a TaskIQ historical sync seeds watched assets into `coins` and backfills `candles`.
- A periodic TaskIQ task incrementally appends new bars for enabled assets.
- The watched asset seed is embedded into backend code; runtime does not depend on any external assignment JSON.
- The Home Assistant addon Dockerfile expects the repository root as build context so it can reuse `backend/`.
