# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Redis Streams event pipeline foundation with `iris_events`, async publisher and consumer-group worker base.
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
- Polling/history writes now publish `candle_inserted` and `candle_closed` into `iris_events` instead of directly driving runtime analytics.
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
- Corrected primary snapshot selection for `coin_metrics` and canonical regime so higher timeframes with insufficient candles no longer override fully-populated lower-timeframe indicators.
- Fixed a runtime import error in the expanded momentum detector family and ensured downstream cluster/hierarchy/context steps see fresh `coin_metrics` values after incremental upserts.
- Sector metric refresh now replaces stale timeframe rows so deleted or reassigned assets do not leave orphaned rotation narratives behind.
