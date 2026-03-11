# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Portfolio Engine with `portfolio_positions`, `portfolio_actions`, `portfolio_state`, ATR-based stops, rebalancing logic and Redis portfolio-state caches.
- Multi-exchange portfolio scaffolding with `exchange_accounts`, `portfolio_balances`, exchange plugin registry and built-in `bybit` / `binance` plugin stubs.
- Portfolio API surface: `/portfolio/positions`, `/portfolio/actions` and `/portfolio/state`.
- Portfolio Map and Portfolio Watch Radar UI showing capital allocation, current positions, regime context, fused IRIS stance, downside risk and unrealized P/L.
- Portfolio / exchange pytest coverage for position sizing, risk limits, sync behavior, plugin loading and auto-watch activation.
- Signal Fusion Engine under `backend/app/analysis/signal_fusion_engine.py` with `market_decisions` storage, Redis decision cache keys `iris:decision:{coin_id}:{timeframe}` and a dedicated `signal_fusion_workers` consumer group.
- Market decision API surface: `/market-decisions`, `/market-decisions/top` and `/coins/{symbol}/market-decision`.
- Decision Radar UI showing fused BUY / SELL / HOLD / WATCH stances, confidence, signal count and regime.
- Signal fusion tests for bullish aggregation, conflicting-stack HOLD behavior, regime-aware weighting and Redis `decision_generated` event emission.
- Pattern Success Engine with pre-write reliability validation between pattern context adjustment and `signals` persistence.
- Regime-aware `pattern_statistics` rows with rolling 200-signal windows, `total_signals`, `successful_signals`, `last_evaluated_at` and per-scope `enabled` flags.
- TaskIQ `pattern_evaluation_job` alias for nightly pattern evaluation plus Redis Stream pattern state events: `pattern_enabled`, `pattern_disabled`, `pattern_degraded`, `pattern_boosted`.
- `signals.market_regime`, `signal_history.market_regime`, `signal_history.profit_after_24h`, `signal_history.profit_after_72h` and `signal_history.maximum_drawdown` for regime-aware outcome tracking.
- Pattern Health Dashboard in the frontend with rolling success rates, active vs disabled detectors and best regime-fit rows.
- Redis Streams event pipeline foundation with `iris_events`, async publisher and consumer-group worker base.
- Integration tests for Redis Stream pipeline, worker ACK/retry and multi-worker distribution using BTC/ETH/SOL candle fixtures.
- Smart Market Scheduling layer with `activity_score`, `activity_bucket`, `analysis_priority`, `last_analysis_at` and Redis Stream `analysis_requested` gating before pattern detection.
- Regime cache in Redis under `iris:regime:{coin_id}:{timeframe}` plus refined regime rules based on ADX, ATR, Bollinger width, 7d price change and EMA50 vs long trend average.
- Pre-signal Pattern Context Layer with dependency filtering and regime-aware confidence adjustment before pattern signals are written to `signals`.
- Market Radar API/UI for HOT coins, emerging coins, recent regime changes and volatility spikes.
- Dedicated pytest coverage for scheduler decisions, regime detection/cache and pattern context filtering.
- TimescaleDB tuning for `candles`: 30-day chunks, hash partitioning by `coin_id` and 90-day compression policy.
- `signal_history` outcome store for evaluated signal returns and drawdowns.
- `feature_snapshots` wide feature-vector table for ML and historical context training.
- Pattern Intelligence foundation schema: feature flags, pattern registry, pattern statistics, discovered patterns, sectors, sector metrics and market cycles.
- Pattern engine package scaffold under `backend/app/patterns` with detector interface, lifecycle enums and priority/temperature helpers.
- Descending candle index `ix_candles_coin_tf_ts_desc` for incremental last-200-candle pattern scans.
- Incremental pattern detection engine with the required structural, continuation, momentum, volatility and volume detector set.
- TaskIQ `patterns_bootstrap_scan` task plus automatic one-time historical bootstrap after coin backfill completes.
- Nightly `pattern_statistics` refresh with temperature decay and automatic lifecycle state transitions.
- Pattern cluster builder, hierarchy builder and contextual signal enrichment with priority scoring inside the existing analytics flow.
- Market regime engine with `bull_trend`, `bear_trend`, `sideways_range`, `high_volatility` and `low_volatility` outputs wired back into `coin_metrics.market_regime`.
- Market Narrative engine for sectors plus Market Cycle engine with stored phase/confidence per coin and timeframe.
- Pattern Discovery engine that clusters rolling window shapes, hashes candidate structures and stores review-only rows in `discovered_patterns`.
- New API surfaces for patterns, per-coin regimes, sector metrics, market cycles and top-ranked signals, plus dashboard/detail page updates for pattern intelligence.
- Manual feature-flag and pattern lifecycle management via API, plus discovery review endpoint for `discovered_patterns`.
- Dashboard now surfaces feature-flag state and discovery candidates, and maintenance jobs re-enrich recent signal context after market structure/statistics updates.
- Detector catalog expanded from the mandatory baseline to 87 grouped pattern detectors across structural, continuation, momentum, volatility and volume families.
- Lazy Investor Decision Engine with `investment_decisions` storage, decision scoring and API endpoints for `/decisions`, `/decisions/top` and `/coins/{symbol}/decision`.
- Home Assistant decision event emission via `iris.decision` with `coin`, `decision`, `confidence` and `reason`.
- Liquidity & Risk Engine with persisted `risk_metrics`, risk-adjusted `final_signals` and API endpoints for `/final-signals`, `/final-signals/top` and `/coins/{symbol}/final-signal`.
- Home Assistant final investment-signal event emission via `iris.investment_signal` with `coin`, `decision`, `confidence`, `risk_score` and `reason`.
- Self Evolving Strategy Engine with `strategies`, `strategy_rules`, `strategy_performance`, discovery job and API endpoints for `/strategies` and `/strategies/performance`.
- Runtime `signal_history` refresh and `feature_snapshots` capture wired into the existing incremental analytics pipeline.
- Backtest API powered by `signal_history` with `/backtests`, `/backtests/top` and `/coins/{symbol}/backtests`.

### Changed
- Event-driven runtime now includes `portfolio_workers` consuming `decision_generated`, `market_regime_changed`, `portfolio_balance_updated` and `portfolio_position_changed`.
- Embedded TaskIQ runtime now also schedules `portfolio_sync_job` every 5 minutes for exchange balance synchronization.
- `coins` API now exposes `auto_watch_enabled` and `auto_watch_source` so portfolio-driven watch activation is visible to the dashboard.
- Event-driven runtime now includes a post-signal fusion layer: `signal_created` / `market_regime_changed` -> `signal_fusion_workers` -> `market_decisions`.
- `signals` now also have a dedicated descending access index `ix_signals_coin_tf_ts` for recent-window fusion reads.
- `pattern_statistics` now use the realized outcome store with rolling windows and regime scopes instead of single global aggregates per timeframe.
- Pattern runtime now validates detections against historical success snapshots before writing `signals`.
- Signal outcome evaluation now stores 24h / 72h profit windows plus maximum drawdown while keeping canonical `result_return` / `result_drawdown` compatibility.
- Polling/history writes now publish `candle_inserted` and `candle_closed` into `iris_events` instead of directly driving runtime analytics.
- Event-driven runtime flow now inserts an `analysis_scheduler_workers` layer between `indicator_updated` and pattern detection so pattern scans only run when requested by activity-aware scheduling.
- Removed the remaining direct `handle_new_candle_event` task/hash path so runtime analytics now has a single Redis Streams execution path.
- Removed the disabled `metrics_service` compatibility shim, its orphan TaskIQ task and unused legacy refresh settings so `coin_metrics` updates now exist only in the event-driven analytics pipeline.
- Pattern statistics now read from persisted `signal_history` outcomes instead of rescanning candle windows on every refresh.
- Extended `signals` with `priority_score`, `context_score` and `regime_alignment`.
- Extended `coins` with `sector_id` mapped from the existing `theme` field so sector analytics can reuse current asset taxonomy.
- Extended `coin_metrics` with persisted `market_regime_details` so regime context is stored per timeframe instead of being recomputed on every read.
- Existing analytics event handling now runs pattern detection on the latest 200 candles whenever a new candle closes.
- Added ranged candle fetch helpers so statistics and context jobs can evaluate historical outcomes without rescanning full tables during normal operation.
- Context scoring now incorporates regime, sector strength and market cycle alignment, and the backend schedules periodic market structure refresh inside the embedded TaskIQ runtime.
- Embedded TaskIQ runtime now also schedules periodic discovery refreshes without introducing any new worker container.
- README now documents the full pattern intelligence architecture, database usage, TaskIQ jobs and frontend/API surface.
- Nightly lifecycle refresh now updates `lifecycle_state` without overriding manual `enabled=false` switches.
- Sector narratives now include capital-wave rotation and the signal/regime APIs use persisted per-timeframe regime details for ranking and display.
- Pattern runtime now refreshes investment decisions after incremental signal detection, market structure refresh and nightly statistics updates.
- Decision runtime now also persists liquidity/risk state and emits risk-adjusted final signals after incremental updates and scheduled refreshes.
- Decision scoring now incorporates active strategy alignment from auto-discovered strategies, and the dashboard shows top strategy performance.

### Fixed
- Restored `indicator_updated` emission from the event-driven analytics pipeline by returning the computed item payloads from `process_indicator_event`.
- Removed a circular import between `patterns.success`, `events.publisher` and `patterns.context` that only surfaced in spawned event workers.
- Corrected primary snapshot selection for `coin_metrics` and canonical regime so higher timeframes with insufficient candles no longer override fully-populated lower-timeframe indicators.
- Fixed a runtime import error in the expanded momentum detector family and ensured downstream cluster/hierarchy/context steps see fresh `coin_metrics` values after incremental upserts.
- Sector metric refresh now replaces stale timeframe rows so deleted or reassigned assets do not leave orphaned rotation narratives behind.
