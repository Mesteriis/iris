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
  Stores OHLCV. Primary key: `coin_id`, `timeframe`, `timestamp`. The table is configured as a TimescaleDB hypertable with a 30-day chunk interval, hash partitioning by `coin_id`, the descending access index `ix_candles_coin_tf_ts_desc`, and a 90-day compression policy.
- `candles_1h`, `candles_4h`, `candles_1d`
  Continuous aggregate views derived from the retained base timeframe so higher-timeframe analytics do not rescan raw 15m history on every request.
- `indicator_cache`
  Stores computed indicators per coin, timeframe and timestamp.
- `coin_metrics`
  Stores current aggregate market state per coin. `market_regime` holds the canonical regime and `market_regime_details` stores persisted per-timeframe regime snapshots used by signal context and `/coins/{symbol}/regime`.
- `signals`
  Stores classic analytics signals, pattern signals, cluster signals and hierarchy signals.
- `signal_history`
  Stores realized signal outcomes with `result_return`, `result_drawdown` and `evaluated_at` so statistics, backtests and strategy research do not need to recalculate forward windows every time.
- `feature_snapshots`
  Stores wide ML-oriented feature vectors per closed candle with regime, cycle, sector strength, pattern density and cluster score.
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
- `investment_decisions`
  Latest and historical lazy-investor decisions derived from signals, regime, sector, cycle and pattern statistics.
- `risk_metrics`
  Liquidity and risk state per coin and timeframe with `liquidity_score`, `slippage_risk` and `volatility_risk`.
- `final_signals`
  Risk-adjusted actionable investment signals derived from `investment_decisions` and `risk_metrics`.
- `strategies`
  Auto-discovered strategy definitions generated from historical signal combinations.
- `strategy_rules`
  Strategy rule rows describing required signal/context alignment.
- `strategy_performance`
  Persisted strategy win rate, return, Sharpe ratio and drawdown.

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
- `decision.py`
  Lazy Investor Decision Engine that converts market analysis into `STRONG_BUY` ... `STRONG_SELL` actions.
- `strategy.py`
  Self Evolving Strategy Engine for strategy discovery, performance tracking and decision alignment.

### Detector families

Implemented detector catalog: 87 pattern detectors.

- Structural:
  `head_shoulders`, `inverse_head_shoulders`, `double_top`, `double_bottom`, `triple_top`, `triple_bottom`, `ascending_triangle`, `descending_triangle`, `symmetrical_triangle`, `rising_wedge`, `falling_wedge`, `rectangle_top`, `rectangle_bottom`, `broadening_top`, `broadening_bottom`, `expanding_triangle`, `descending_channel_breakout`, `ascending_channel_breakdown`, `rounded_bottom`, `rounded_top`, `diamond_bottom`, `diamond_top`, `flat_base`
- Continuation:
  `bull_flag`, `bear_flag`, `pennant`, `cup_and_handle`, `breakout_retest`, `consolidation_breakout`, `high_tight_flag`, `falling_channel_breakout`, `rising_channel_breakdown`, `measured_move_bullish`, `measured_move_bearish`, `base_breakout`, `volatility_contraction_breakout`, `volatility_contraction_breakdown`, `pullback_continuation_bullish`, `pullback_continuation_bearish`, `squeeze_breakout`, `trend_pause_breakout`, `handle_breakout`, `stair_step_continuation`
- Momentum:
  `rsi_divergence`, `macd_cross`, `macd_divergence`, `momentum_exhaustion`, `rsi_reclaim`, `rsi_rejection`, `rsi_failure_swing_bullish`, `rsi_failure_swing_bearish`, `macd_zero_cross_bullish`, `macd_zero_cross_bearish`, `macd_histogram_expansion_bullish`, `macd_histogram_expansion_bearish`, `trend_acceleration`, `trend_deceleration`
- Volatility:
  `bollinger_squeeze`, `bollinger_expansion`, `atr_spike`, `volatility_compression`, `volatility_expansion_breakout`, `atr_compression`, `atr_release`, `narrow_range_breakout`, `band_walk_bullish`, `band_walk_bearish`, `mean_reversion_snap`, `volatility_reversal_bullish`, `volatility_reversal_bearish`
- Volume:
  `volume_spike`, `volume_climax`, `volume_divergence`, `volume_dry_up`, `volume_breakout_confirmation`, `accumulation_volume`, `distribution_volume`, `churn_bar`, `effort_result_divergence_bullish`, `effort_result_divergence_bearish`, `relative_volume_breakout`, `volume_follow_through_bullish`, `volume_follow_through_bearish`, `buying_climax`, `selling_climax`, `volume_trend_confirmation_bullish`, `volume_trend_confirmation_bearish`

Signals use `signal_type` values such as:

- `pattern_head_shoulders`
- `pattern_bull_flag`
- `pattern_volume_spike`
- `pattern_cluster_bullish`
- `pattern_hierarchy_accumulation`

## Runtime flow

### Incremental path

1. New closed candle is written into `candles`.
2. Timescale continuous aggregates keep 1h, 4h and 1d views ready for higher-timeframe reads.
3. Existing analytics pipeline updates indicators and `coin_metrics`.
4. The same pipeline persists per-timeframe `indicator_cache` rows.
5. Pattern engine loads the last 200 candles and runs enabled detectors.
6. Cluster and hierarchy engines derive stronger structures from emitted pattern signals.
7. Regime and cycle context are applied.
8. Contextual Signal Engine updates:
   `priority_score = confidence * temperature * regime_alignment * volatility_alignment * liquidity_score * sector_alignment * cycle_alignment * cluster_bonus`
9. Lazy Investor Decision Engine converts the current stack into an investment decision.
10. Liquidity & Risk Engine converts that decision into a tradable `final_signal`.
11. `signal_history` refresh evaluates matured signals and persists forward return / drawdown outcomes.
12. `feature_snapshots` capture the closed-candle feature vector for ML, research and backtests.

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

The backend stores the canonical regime in `coin_metrics.market_regime`, persists per-timeframe snapshots in `coin_metrics.market_regime_details`, and exposes those snapshots through the API.

### Market Narrative Engine

The sector layer reuses the current `theme` taxonomy by mapping it into `sectors` and `coins.sector_id`. `sector_metrics` tracks:

- `sector_strength`
- `relative_strength`
- `capital_flow`
- `volatility`

Narratives expose BTC dominance bias, sector leadership state and capital-wave rotation (`btc`, `large_caps`, `sector_leaders`, `mid_caps`, `micro_caps`) for the dashboard.

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

## Lazy Investor Decision Engine

The decision layer aggregates:

- pattern signals
- pattern clusters
- hierarchy signals
- market regime
- sector narrative
- market cycle
- historical pattern statistics

Supported decisions:

- `STRONG_BUY`
- `BUY`
- `ACCUMULATE`
- `HOLD`
- `REDUCE`
- `SELL`
- `STRONG_SELL`

Stored table:

- `investment_decisions`

Decision score formula:

- `decision_score = signal_priority * regime_alignment * sector_strength * cycle_alignment * historical_pattern_success`

Runtime triggers:

- new signal detected inside incremental candle processing
- new cluster / hierarchy emission
- market regime refresh
- sector strength refresh
- market cycle refresh
- nightly pattern statistics refresh

The Home Assistant integration polls decision updates and fires `iris.decision` with:

- `coin`
- `decision`
- `confidence`
- `reason`

## Liquidity & Risk Engine

The liquidity/risk layer evaluates whether a decision is actually tradable for a lazy investor.

Stored tables:

- `risk_metrics`
- `final_signals`

Risk metrics:

- `liquidity_score`
  Computed from `volume_24h` and `market_cap`.
- `slippage_risk`
  Computed from the `volume / liquidity` turnover proxy.
- `volatility_risk`
  Computed from `ATR / price` using the latest timeframe snapshot.

Risk-adjusted score formula:

- `risk_adjusted_score = decision_score * liquidity_score * (1 - slippage_risk) * (1 - volatility_risk)`

Runtime behavior:

- Reuses `coin_metrics.volume_24h`, `coin_metrics.market_cap` and timeframe ATR data from `indicator_cache`.
- Runs immediately after decision generation inside the existing new-candle pipeline.
- Re-runs after nightly decision refreshes and market-structure refreshes inside the same embedded TaskIQ runtime.
- Stores the latest risk state in `risk_metrics` and historical actionable outputs in `final_signals`.

The Home Assistant integration also polls final-signal updates and fires `iris.investment_signal` with:

- `coin`
- `decision`
- `confidence`
- `risk_score`
- `reason`

## Self Evolving Strategy Engine

The strategy layer automatically discovers profitable signal combinations and feeds them back into the decision stack.

Stored tables:

- `strategies`
- `strategy_rules`
- `strategy_performance`

Discovery inputs:

- pattern signals
- cluster signals
- hierarchy signals
- locally derived market regime
- sector context
- market cycle context
- realized forward returns and drawdowns

Strategy evaluation metrics:

- `win_rate`
- `avg_return`
- `sharpe_ratio`
- `max_drawdown`

Runtime behavior:

- `strategy_discovery_job` scans historical pattern stacks and future outcomes.
- It discovers single-token and two-token combinations plus regime/sector/cycle context.
- Only strategies above the configured performance thresholds are marked `enabled`.
- Active strategies are reused by the Lazy Investor Decision Engine through `strategy_alignment`.
- Matching active strategies increase decision score and confidence.

## Signal History And Backtests

The data architecture now follows:

- `candles -> continuous aggregates -> indicator_cache -> signals -> signal_history -> pattern statistics / feature_snapshots -> decisions / backtests / ML`

`signal_history` is the canonical realized-outcome store. It allows IRIS to:

- compute pattern temperature from persisted outcomes
- rank signal families by ROI, win rate and Sharpe ratio
- feed strategy discovery with stable historical performance data
- build ML datasets from `feature_snapshots` without joining raw candle windows repeatedly

The backtest layer is an API read model over `signal_history`, not a separate worker subsystem.

## API

Primary endpoints:

- `GET /signals`
- `GET /signals/top`
- `GET /decisions`
- `GET /decisions/top`
- `GET /final-signals`
- `GET /final-signals/top`
- `GET /strategies`
- `GET /strategies/performance`
- `GET /backtests`
- `GET /backtests/top`
- `GET /patterns`
- `GET /patterns/features`
- `PATCH /patterns/features/{feature_slug}`
- `PATCH /patterns/{slug}`
- `GET /patterns/discovered`
- `GET /coins/{symbol}/patterns`
- `GET /coins/{symbol}/backtests`
- `GET /coins/{symbol}/decision`
- `GET /coins/{symbol}/final-signal`
- `GET /coins/{symbol}/regime`
- `GET /sectors`
- `GET /sectors/metrics`
- `GET /market/cycle`

The frontend uses these endpoints to show:

- active patterns
- feature flag state
- priority-ranked signals
- lazy-investor decisions
- self-evolving top strategies
- backtested signal families
- cluster membership
- market regime
- cycle phase
- sector rotation
- capital wave narrative
- pattern history
- discovery candidates for manual review

## Performance notes

- Candle history is never duplicated.
- Incremental detection reads the last 200 candles from `candles` / aggregate views.
- `ix_candles_coin_tf_ts_desc` accelerates the last-200-candle query pattern.
- Higher timeframes are served from continuous aggregates instead of rebuilding 1h / 4h / 1d candles from the raw table on every read.
- `signal_history` removes repeated forward-window scans from nightly statistics refreshes.
- `feature_snapshots` keep ML-oriented context vectors in a single table keyed by `coin_id`, `timeframe`, `timestamp`.
- Timescale compression keeps long-horizon candle retention practical for multi-year history.
- Runtime scans full retained history only during bootstrap or scheduled discovery/statistics jobs, not during normal incremental operation.

## Notes

- TaskIQ workers run inside the backend service lifecycle. There is no separate worker container.
- The backend applies Alembic migrations during startup.
- On startup, a TaskIQ historical sync seeds watched assets into `coins` and backfills `candles`.
- A periodic TaskIQ task incrementally appends new bars for enabled assets.
- The watched asset seed is embedded into backend code; runtime does not depend on any external assignment JSON.
- The Home Assistant addon Dockerfile expects the repository root as build context so it can reuse `backend/`.
