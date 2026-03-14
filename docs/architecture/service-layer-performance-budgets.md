# Service-Layer Performance Budgets

## Scope

This document defines performance budgets for the heavy service-layer sync and job paths that already have explicit runtime ownership, locks or tracked-operation boundaries.

The budgets are intentionally practical:

- `target` is the normal operating envelope;
- `alert` means the path is degrading and should page/emit an operational signal;
- `hard` is the maximum tolerated runtime before the path must be split, chunked or rescheduled.

For TaskIQ jobs, the `hard` budget must never exceed the effective Redis lock timeout for the same path.

## Global Rules

1. A service/job path that is forecast to exceed its hard budget must be chunked or delegated to a longer-running workflow, not left inline.
2. Alert budget breaches should produce telemetry before lock timeouts are exhausted.
3. Long-running sweeps must preserve restartability and partial-progress safety.
4. Budget reviews happen when a path changes batching strategy, upstream provider mix or fan-out behavior.

## Budget Matrix

| Domain / path | Target | Alert | Hard | Operational note |
| --- | --- | --- | --- | --- |
| `market_data` coin history sync (`run_coin_history_job`, keyed coin sync) | `5m` | `15m` | `30m` | Hard budget aligns with `COIN_HISTORY_LOCK_TIMEOUT_SECONDS`; if a single coin needs longer, split backfill windows. |
| `market_data` latest history refresh sweep | `5m` | `10m` | `15m` | Must stay inside `HISTORY_REFRESH_LOCK_TIMEOUT_SECONDS`; provider stalls should fall back to later refresh rather than hold the global sweep lock. |
| `market_data` history backfill sweep | `15m` | `45m` | `60m` | Uses the longest global lock; wide backfills should chunk by symbol groups and resume safely. |
| `market_structure` single-source poll | `30s` | `90s` | `120s` | Must fit the per-source poll lock. |
| `market_structure` enabled-source poll sweep | `2m` | `4m` | `5m` | Sweep must not monopolize the global enabled-poll lock. |
| `market_structure` source health refresh | `30s` | `2m` | `3m` | Health refresh is lightweight; sustained overruns indicate source-count growth or hidden IO drift. |
| `news` single-source poll | `30s` | `90s` | `120s` | Bound by per-source poll lock and upstream provider responsiveness. |
| `news` enabled-source poll sweep | `2m` | `4m` | `5m` | Cursor-driven sweeps should remain incremental; oversized source sets must shard rather than extend the lock. |
| `portfolio` balance sync | `1m` | `3m` | `4m` | Hard budget equals `PORTFOLIO_SYNC_LOCK_TIMEOUT_SECONDS`; exchange fan-out must stay bounded. |
| `predictions` pending-evaluation sweep | `1m` | `4m` | `5m` | If evaluation volume grows, batch windows must split rather than hold the singleton evaluation lock. |
| `anomalies` enrichment / sector / market-structure scans | `1m` | `4m` | `5m` | Keyed scans are safe to rerun; long anomaly batches should partition by trigger tuple. |
| `hypothesis_engine` evaluation sweep | `1m` | `4m` | `5m` | Operation-tracked evaluation should surface long-running status before the singleton lock is exhausted. |
| `patterns` bootstrap / statistics / market-structure refresh | `30m` | `90m` | `120m` | These are intentionally heavyweight analytics jobs; over-budget runs must checkpoint and resume instead of expanding lock time. |
| `patterns` discovery / strategy discovery | `60m` | `180m` | `240m` | Discovery is the longest-running path; hard budget aligns with the existing 4h locks and should not grow further without repartitioning. |

## Review Checklist

- Does the path have a target/alert/hard budget recorded here?
- Is the hard budget still below or equal to the real runtime lock/operation boundary?
- If the path exceeded alert budget, was the cause batching, provider latency or hidden cross-domain fan-out?
- If the path approaches hard budget, can it be chunked or resumed without violating ADR 0010 and ADR 0014?
