# Service-Layer Runtime Policies

## Scope

This document fixes idempotency, retry and concurrency rules for service-layer orchestration paths that run in jobs, consumers or tracked async operations.

These rules apply on top of ADR 0010 and ADR 0014:

- callers own commit boundaries;
- state-coupled side effects execute only after commit;
- reruns must be safe or explicitly rejected.

## Global Rules

1. Task entry points must prefer explicit deduplication over optimistic reruns.
2. Redis task locks are the default concurrency guard for singleton or keyed background work.
3. When an external caller needs status visibility, the task path must use `OperationStore` and surface deduplication/active-operation semantics explicitly.
4. Stream consumers rely on `event.idempotency_key` and the group-level processed-event ledger in `src/runtime/streams/consumer.py`.
5. Retryable upstream failures should re-enter through the scheduler/backoff path, not by inline unbounded retry loops inside service code.
6. A lock miss is treated as a typed `skipped` outcome, not as a hidden best-effort duplicate run.

## Domain Matrix

| Domain | Entry points | Idempotency / dedup rule | Retry / backoff rule | Concurrency rule |
| --- | --- | --- | --- | --- |
| `market_data` | `bootstrap_observed_coins_history`, `backfill_observed_coins_history`, `refresh_observed_coins_history`, `run_coin_history_job` | Global backfill/latest sweeps use singleton Redis locks; coin sync is additionally keyed by `symbol`; manual runs use `OperationStore` and may be deduplicated by operation identity. | Respect `retry_at` returned by history sync results and provider cooldowns; requeue through scheduler rather than inline loops. | Only one global backfill, one global latest refresh and one keyed coin-history sync may run at a time. |
| `market_structure` | `poll_market_structure_source_job`, `poll_enabled_market_structure_sources_job`, `refresh_market_structure_source_health_job` | Per-source polling deduplicates on `source_id`; enabled poll and health refresh are singleton jobs; externally tracked jobs use `OperationStore`. | Health engine owns `backoff_until` and failure escalation; callers should retry only after backoff clears. | Source polling lock key is per source; enabled sweep and health refresh each have their own singleton lock. |
| `news` | `poll_news_source_job`, `poll_enabled_news_sources_job` | Per-source polls deduplicate on `source_id`; enabled sweep is singleton; source cursor state makes safe reruns incremental. | Retry via next scheduled poll or explicit rerun after upstream/provider recovery; avoid inline provider retry loops in task code. | One keyed source poll and one global enabled-sources sweep at a time. |
| `patterns` | `patterns_bootstrap_scan`, `pattern_evaluation_job`, `update_pattern_statistics`, `refresh_market_structure`, `run_pattern_discovery`, `strategy_discovery_job` | Bootstrap deduplicates per `symbol` or `all`; other analytics refresh jobs are singleton by job type. | Long-running analytics refreshes should restart from persisted state or rerunnable scans, not hidden in-memory retries. | Bootstrap/statistics/market-structure/discovery/strategy jobs each own a dedicated Redis lock key with long timeouts. |
| `predictions` | `prediction_evaluation_job` | Singleton evaluation lock; duplicate triggers return `skipped`. | Retry by rescheduling evaluation, not by nested retry loops around service execution. | Only one prediction evaluation sweep may run at a time. |
| `portfolio` | `portfolio_sync_job` | Singleton sync lock; reruns are safe because balances are reconciled into the same rows/positions before post-commit side effects. | Retry via scheduler or manual rerun after exchange/provider recovery. | Only one portfolio sync may run at a time. |
| `anomalies` | `anomaly_enrichment_job`, `sector_anomaly_scan`, `market_structure_anomaly_scan` | Enrichment deduplicates per `anomaly_id`; scans deduplicate on `(trigger_coin_id, timeframe, timestamp)` tuple. | Retry only by re-enqueueing the same keyed task; repeated scans must preserve the same trigger tuple. | One enrichment per anomaly and one keyed sector/market-structure scan per trigger tuple. |
| `hypothesis_engine` | `evaluate_hypotheses_job` | Singleton evaluation lock plus `OperationStore` for externally visible reruns. | Retry through the scheduler after terminal failure analysis; no hidden retries in evaluation service. | Only one hypothesis evaluation sweep may run at a time. |

## Stream Consumers

- Event-stream workers deduplicate by `group_name + event.idempotency_key`.
- Consumer handlers must remain reentrant because Redis stream delivery can replay before acknowledgement.
- If a consumer fans out to background jobs, the downstream job must still enforce its own Redis lock or tracked-operation boundary.

## Review Checklist

- Is the lock key scoped to the real concurrency resource?
- Does a duplicate trigger return a typed `skipped` or deduplicated result?
- Is retry delegated to scheduler/backoff/operation-store flow instead of hidden loops?
- Are post-commit side effects still outside the locked write section?
