# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
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

### Changed
- Extended `signals` with `priority_score`, `context_score` and `regime_alignment`.
- Extended `coins` with `sector_id` mapped from the existing `theme` field so sector analytics can reuse current asset taxonomy.
- Existing analytics event handling now runs pattern detection on the latest 200 candles whenever a new candle closes.
- Added ranged candle fetch helpers so statistics and context jobs can evaluate historical outcomes without rescanning full tables during normal operation.
- Context scoring now incorporates regime, sector strength and market cycle alignment, and the backend schedules periodic market structure refresh inside the embedded TaskIQ runtime.
- Embedded TaskIQ runtime now also schedules periodic discovery refreshes without introducing any new worker container.
- README now documents the full pattern intelligence architecture, database usage, TaskIQ jobs and frontend/API surface.
- Nightly lifecycle refresh now updates `lifecycle_state` without overriding manual `enabled=false` switches.
