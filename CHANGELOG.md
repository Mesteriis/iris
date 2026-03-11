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

### Changed
- Extended `signals` with `priority_score`, `context_score` and `regime_alignment`.
- Extended `coins` with `sector_id` mapped from the existing `theme` field so sector analytics can reuse current asset taxonomy.
- Existing analytics event handling now runs pattern detection on the latest 200 candles whenever a new candle closes.
