# IRIS

IRIS is a market intelligence service built on top of the existing `coins`, `candles`, `indicator_cache`, `coin_metrics` and `signals` schema. The system keeps one canonical candle store and layers analytics, pattern intelligence and market structure on top of it.

The runtime is now hybrid:

- market data ingestion stays polling-driven
- internal analytics runs through Redis Streams events

## Stack

- FastAPI backend with SQLAlchemy, Alembic and embedded TaskIQ runtime
- Vue 3 dashboard with Pinia, Tailwind, Vite and ECharts
- PostgreSQL / TimescaleDB candle storage
- Redis Streams event bus for internal analytics
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
- `iris_events` Redis Stream
  Internal event bus for `candle_closed`, `indicator_updated`, `pattern_detected`, `pattern_cluster_detected`, `market_regime_changed`, `decision_generated` and `signal_created`.
- `signal_history`
  Stores realized signal outcomes with `market_regime`, `profit_after_24h`, `profit_after_72h`, `maximum_drawdown`, `result_return`, `result_drawdown` and `evaluated_at` so statistics, backtests and strategy research do not need to recalculate forward windows every time.
- `feature_snapshots`
  Stores wide ML-oriented feature vectors per closed candle with regime, cycle, sector strength, pattern density and cluster score.
- `pattern_features`
  Feature flags for `pattern_detection`, `pattern_clusters`, `pattern_hierarchy`, `market_regime_engine`, `pattern_discovery_engine`.
- `pattern_registry`
  Pattern lifecycle registry with `ACTIVE`, `EXPERIMENTAL`, `COOLDOWN`, `DISABLED`.
- `pattern_statistics`
  Pattern performance snapshots with rolling-window `sample_size`, `total_signals`, `successful_signals`, `success_rate`, `avg_return`, `avg_drawdown`, `temperature`, `market_regime`, `last_evaluated_at` and per-scope `enabled`.
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
- `market_decisions`
  Fused BUY / SELL / HOLD / WATCH outputs aggregated from recent `signals` per coin and timeframe.
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
- `exchange_accounts`
  Registered exchange accounts used by plugin-based portfolio synchronization.
- `portfolio_balances`
  Raw balances per exchange account, symbol and coin.
- `portfolio_positions`
  Portfolio positions with exchange source, position type, ATR-based stops and status tracking.
- `portfolio_actions`
  Portfolio actions linked to the fused `market_decisions` they came from.
- `portfolio_state`
  Capital allocation state mirrored into Redis for fast dashboard reads.

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
  Nightly pattern statistics refresh, rolling success windows, temperature decay and pattern state events.
- `success.py`
  Pattern Success Engine validation layer that can suppress, degrade or boost detections before signal persistence.
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
- `portfolio/engine.py`
  Portfolio Engine for position sizing, rebalancing, capital allocation, exchange balance sync and auto-watch activation.

## Portfolio Engine

The portfolio layer consumes existing `market_decisions` and does not modify candles, indicators, patterns, context, success validation or signal fusion.

Stored tables:

- `portfolio_positions`
- `portfolio_actions`
- `portfolio_state`
- `exchange_accounts`
- `portfolio_balances`

Responsibilities:

- convert fused `BUY / SELL / HOLD / WATCH` decisions into portfolio actions
- size positions from confidence, regime and volatility
- enforce portfolio-wide capital and exposure limits
- maintain ATR-based stop loss / take profit levels
- synchronize exchange balances through plugins
- auto-enable watched coins when real holdings cross a USD threshold

Supported actions:

- `OPEN_POSITION`
- `CLOSE_POSITION`
- `REDUCE_POSITION`
- `INCREASE_POSITION`
- `HOLD_POSITION`

Portfolio rules:

- max position size: 5% of total capital
- max positions: 20
- max sector exposure: configurable
- no allocation beyond `portfolio_state.available_capital`

Position sizing:

- `position_size = base_size * decision_confidence * regime_factor * volatility_adjustment`

Stops:

- `stop_loss = entry_price - atr_14 * portfolio_stop_atr_multiplier`
- `take_profit = entry_price + atr_14 * portfolio_take_profit_atr_multiplier`

Redis caches:

- `iris:portfolio:state`
- `iris:portfolio:balances`

### Multi-exchange support

Exchange integrations live under `backend/app/exchanges`:

- `base.py`
  abstract `ExchangePlugin` contract
- `registry.py`
  automatic plugin registration and instantiation
- `bybit.py`
  current exchange scaffold
- `binance.py`
  additional plugin scaffold proving the plugin architecture

This keeps the portfolio engine open for `Kraken`, `Coinbase`, `OKX` and other exchanges without changing the portfolio core.

## Signal Fusion Engine

The fusion layer lives under `backend/app/analysis/signal_fusion_engine.py` and sits on top of stored `signals`. It does not replace pattern signals or investment decisions. It adds a separate aggregation layer that turns recent signal stacks into a unified market stance.

Responsibilities:

- read the latest 1-3 closed-candle signal groups from `signals`
- weight each signal by confidence, historical pattern success, signal context and regime compatibility
- resolve agreement vs conflict across bullish and bearish signals
- persist fused rows into `market_decisions`
- mirror latest decisions into Redis cache keys `iris:decision:{coin_id}:{timeframe}`
- emit `decision_generated` with `source=signal_fusion`

Decision outcomes:

- `BUY`
- `SELL`
- `HOLD`
- `WATCH`

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

### Event-driven analytics

The internal pipeline is event-driven and producer/consumer decoupled:

1. Polling jobs fetch market candles.
2. Polling inserts candles into `candles`.
3. Polling publishes `candle_inserted` and `candle_closed` into `iris_events`.
4. `indicator_workers` consume `candle_closed`, compute indicators and emit `indicator_updated`.
5. `analysis_scheduler_workers` consume `indicator_updated`, evaluate `activity_score` / `activity_bucket` and emit `analysis_requested` only when the coin should be analyzed now.
6. `pattern_workers` consume `analysis_requested`, run incremental pattern detection and emit `pattern_detected` / `pattern_cluster_detected`.
7. `regime_workers` consume `indicator_updated`, refresh market regime context and emit `market_regime_changed`.
8. `decision_workers` consume pattern/regime/signal events, enrich context, generate decisions/final signals and emit `decision_generated`.
9. `signal_fusion_workers` consume recent signal/regime events, fuse recent stacks and persist `market_decisions`.
10. `portfolio_workers` consume fused decisions, regime changes and portfolio balance events to maintain positions and actions.

Workers use Redis Streams consumer groups:

- `indicator_workers`
- `analysis_scheduler_workers`
- `pattern_workers`
- `regime_workers`
- `decision_workers`
- `signal_fusion_workers`
- `portfolio_workers`

Each worker only ACKs after processing. Stale pending messages are reclaimed with `XAUTOCLAIM`, so crash recovery does not lose events.

There is no parallel legacy analytics trigger path. Runtime candle analytics now enters the system only through `iris_events`.

### Incremental path

1. New closed candle is written into `candles` by polling.
2. Timescale continuous aggregates keep 1h, 4h and 1d views ready for higher-timeframe reads.
3. `indicator_workers` update indicators and `coin_metrics`.
4. The same stage persists per-timeframe `indicator_cache` rows.
5. `analysis_scheduler_workers` compute activity buckets: `HOT`, `WARM`, `COLD`, `DEAD`.
6. `pattern_workers` load the last 200 candles and run enabled detectors only when `analysis_requested` arrives.
7. Pattern Context Layer filters detectors with missing dependencies and adjusts confidence with regime-aware weights.
8. Pattern Success Engine validates the adjusted detections against rolling historical success snapshots, can suppress weak regimes, degrade confidence or boost high-performing setups, and only then persists pattern signals.
9. Cluster and hierarchy engines derive stronger structures from emitted pattern signals.
10. `regime_workers` update cycle and sector-aware market context and mirror regime reads into Redis cache keys `iris:regime:{coin_id}:{timeframe}`.
11. `decision_workers` update the Contextual Signal Engine:
   `priority_score = confidence * temperature * regime_alignment * volatility_alignment * liquidity_score * sector_alignment * cycle_alignment * cluster_bonus`
12. Lazy Investor Decision Engine converts the current stack into an investment decision.
13. Liquidity & Risk Engine converts that decision into a tradable `final_signal`.
14. `signal_fusion_workers` aggregate the last 1-3 signal groups into `market_decisions` and cache them under `iris:decision:{coin_id}:{timeframe}`.
15. `signal_history` refresh evaluates matured signals and persists 24h / 72h return windows plus drawdown outcomes.
16. `feature_snapshots` capture the closed-candle feature vector for ML, research and backtests.
17. `portfolio_workers` convert fused market decisions plus portfolio balance changes into capital actions and live positions.

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
- `pattern_evaluation_job`
  Compatibility alias for the nightly Pattern Success Engine evaluation job.
- `refresh_market_structure`
  Periodic sector metrics and market cycle refresh.
- `run_pattern_discovery`
  Periodic discovery candidate refresh.
- `signal_context_enrichment`
  Recomputes signal context on demand.
- `portfolio_sync_job`
  Every 5 minutes, synchronizes balances from enabled exchange accounts, updates portfolio tables and emits balance-change events.

Event workers are started by the backend runtime as separate worker processes inside the same backend service. They do not require a dedicated container.

## Market structure layers

### Smart Market Scheduling

`coin_metrics` now stores:

- `activity_score`
- `activity_bucket`
- `analysis_priority`
- `last_analysis_at`

Activity score is derived from normalized 24h price change, volatility and 24h volume change. The scheduler uses that score to bucket assets:

- `HOT`: analyze every candle
- `WARM`: analyze every 2 candles
- `COLD`: analyze every 10 candles
- `DEAD`: analyze at most once per hour

This keeps the event-driven pattern pipeline scalable without changing the canonical polling -> candles -> indicators -> patterns -> signals flow.

### Market Regime Engine

Regimes:

- `bull_trend`
- `bear_trend`
- `sideways_range`
- `high_volatility`
- `low_volatility`

The backend stores the canonical regime in `coin_metrics.market_regime`, persists per-timeframe snapshots in `coin_metrics.market_regime_details`, mirrors them into Redis cache keys `iris:regime:{coin_id}:{timeframe}`, and exposes those snapshots through the API.

### Pattern Context Layer

The Pattern Context Layer runs before pattern signals are inserted:

- checks detector dependencies such as trend / volume prerequisites
- skips patterns when required context is missing
- weights pattern confidence by the active market regime

Examples:

- continuation patterns are boosted in `bull_trend` / `bear_trend`
- reversal patterns are reduced when they fight the current trend
- volatility breakout patterns are boosted in `high_volatility`
- mean-reversion patterns are favored in `sideways_range`

### Pattern Success Engine

After context adjustment and before `signals` persistence, IRIS validates each detection against rolling realized outcomes from `signal_history`.

- Uses a rolling window of the latest 200 mature signals per `pattern_slug`, `timeframe` and optional `market_regime`.
- Tracks `total_signals`, `successful_signals`, `success_rate`, `avg_return`, `avg_drawdown`, `temperature` and `last_evaluated_at`.
- Can suppress weak detections, degrade confidence below neutral thresholds, or boost high-performing setups.
- Publishes Redis Stream state events:
  `pattern_enabled`, `pattern_disabled`, `pattern_degraded`, `pattern_boosted`

The nightly evaluation job updates `pattern_statistics`, refreshes lifecycle state and keeps the runtime validator aligned with recent market behavior.

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
- compute 24h / 72h success windows and maximum drawdown without rescanning raw history for every statistic read
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
- `GET /market-decisions`
- `GET /market-decisions/top`
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
- `GET /coins/{symbol}/market-decision`
- `GET /coins/{symbol}/final-signal`
- `GET /coins/{symbol}/regime`
- `GET /sectors`
- `GET /sectors/metrics`
- `GET /market/cycle`
- `GET /market/radar`
- `GET /portfolio/positions`
- `GET /portfolio/actions`
- `GET /portfolio/state`

The frontend uses these endpoints to show:

- active patterns
- feature flag state
- priority-ranked signals
- lazy-investor decisions
- fused market decisions with Decision Radar
- self-evolving top strategies
- backtested signal families
- cluster membership
- market regime
- cycle phase
- sector rotation
- capital wave narrative
- HOT coins and emerging coins
- recent regime changes
- volatility spikes
- Portfolio Map with capital allocation, current positions, risk-to-stop and unrealized P/L
- Portfolio Watch Radar with held assets, regime, fused IRIS stance and risk
- Pattern Health Dashboard with rolling success rates, active / disabled detector counts and best regime-fit rows
- pattern history
- discovery candidates for manual review

## Testing

Redis Stream pipeline coverage is implemented with `pytest` and `pytest-asyncio`.

Current integration tests cover:

- polling-style candle insert publishing `candle_inserted` and `candle_closed`
- producer -> `indicator_workers` -> `analysis_scheduler_workers` -> `pattern_workers` -> signal creation
- multi-worker distribution in the same consumer group
- ACK and retry semantics after a simulated worker crash
- scheduler activity-score calculation and bucket assignment
- regime detection rules and Redis regime cache
- pattern dependency filtering and regime-aware context adjustment
- signal fusion aggregation, conflict handling, regime weighting and Redis decision events
- portfolio position creation, rebalance actions and ATR stop calculation
- portfolio risk limits for max positions and sector exposure
- exchange plugin registry loading and exchange balance synchronization
- auto-watch activation for portfolio-held assets

The test fixture uses real 15m OHLCV candles for:

- BTC
- ETH
- SOL

## Performance notes

- Candle history is never duplicated.
- Incremental detection reads the last 200 candles from `candles` / aggregate views.
- `ix_candles_coin_tf_ts_desc` accelerates the last-200-candle query pattern.
- Signal fusion reads only recent `signals` windows through `ix_signals_coin_tf_ts`.
- Portfolio state and portfolio balances are mirrored into Redis so dashboard refreshes do not have to hit SQL for every poll.
- Higher timeframes are served from continuous aggregates instead of rebuilding 1h / 4h / 1d candles from the raw table on every read.
- `signal_history` removes repeated forward-window scans from nightly statistics refreshes.
- `feature_snapshots` keep ML-oriented context vectors in a single table keyed by `coin_id`, `timeframe`, `timestamp`.
- Timescale compression keeps long-horizon candle retention practical for multi-year history.
- Event workers operate only on the last 200 candles during runtime and do not rescan full history for every event.
- Runtime scans full retained history only during bootstrap or scheduled discovery/statistics jobs, not during normal incremental operation.
- Coin-detail Decision Radar can reuse Redis cache keys `iris:decision:{coin_id}:{timeframe}` instead of forcing PostgreSQL reads on every refresh.

## Notes

- TaskIQ workers run inside the backend service lifecycle. There is no separate worker container.
- The backend applies Alembic migrations during startup.
- On startup, a TaskIQ historical sync seeds watched assets into `coins` and backfills `candles`.
- A periodic TaskIQ task incrementally appends new bars for enabled assets.
- The watched asset seed is embedded into backend code; runtime does not depend on any external assignment JSON.
- The Home Assistant addon Dockerfile expects the repository root as build context so it can reuse `backend/`.
