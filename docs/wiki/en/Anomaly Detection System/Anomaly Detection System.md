# Anomaly Detection System

<cite>
**Referenced Files in This Document**
- [src/apps/anomalies/detectors/__init__.py](file://src/apps/anomalies/detectors/__init__.py)
- [src/apps/anomalies/detectors/compression_expansion_detector.py](file://src/apps/anomalies/detectors/compression_expansion_detector.py)
- [src/apps/anomalies/detectors/correlation_breakdown_detector.py](file://src/apps/anomalies/detectors/correlation_breakdown_detector.py)
- [src/apps/anomalies/detectors/cross_exchange_dislocation_detector.py](file://src/apps/anomalies/detectors/cross_exchange_dislocation_detector.py)
- [src/apps/anomalies/detectors/failed_breakout_detector.py](file://src/apps/anomalies/detectors/failed_breakout_detector.py)
- [src/apps/anomalies/detectors/funding_open_interest_detector.py](file://src/apps/anomalies/detectors/funding_open_interest_detector.py)
- [src/apps/anomalies/detectors/liquidation_cascade_detector.py](file://src/apps/anomalies/detectors/liquidation_cascade_detector.py)
- [src/apps/anomalies/detectors/price_spike_detector.py](file://src/apps/anomalies/detectors/price_spike_detector.py)
- [src/apps/anomalies/detectors/price_volume_divergence_detector.py](file://src/apps/anomalies/detectors/price_volume_divergence_detector.py)
- [src/apps/anomalies/detectors/relative_divergence_detector.py](file://src/apps/anomalies/detectors/relative_divergence_detector.py)
- [src/apps/anomalies/detectors/synchronous_move_detector.py](file://src/apps/anomalies/detectors/synchronous_move_detector.py)
- [src/apps/anomalies/scoring/anomaly_scorer.py](file://src/apps/anomalies/scoring/anomaly_scorer.py)
- [src/apps/anomalies/services/anomaly_service.py](file://src/apps/anomalies/services/anomaly_service.py)
- [src/apps/anomalies/policies.py](file://src/apps/anomalies/policies.py)
- [src/apps/anomalies/models.py](file://src/apps/anomalies/models.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)
10. [Appendices](#appendices)

## Introduction
This document describes the anomaly detection subsystem that identifies unusual market behavior across multiple dimensions: price dynamics, volume behavior, volatility regimes, correlation shifts, derivatives fundamentals, cross-venue dislocations, and sector synchronicity. It covers the detector algorithms, scoring methodology, severity classification, alert generation workflow, policy-based filtering, and real-time and historical analysis capabilities.

## Project Structure
The anomaly detection system is organized around detectors, a scoring module, a policy engine, a service orchestrator, persistence models, and supporting schemas/constants. Detectors encapsulate algorithmic logic per anomaly type. The service coordinates detection passes, applies scoring and policy decisions, persists anomalies, and emits alerts. Persistence models define database tables for anomalies and market structure snapshots.

```mermaid
graph TB
subgraph "Detectors"
D1["Compression/Expansion"]
D2["Correlation Breakdown"]
D3["Cross-Exchange Dislocation"]
D4["Failed Breakout"]
D5["Funding/Open Interest"]
D6["Liquidation Cascade"]
D7["Price Spike"]
D8["Price-Volume Divergence"]
D9["Relative Divergence"]
D10["Synchronous Move"]
end
S["AnomalyService"]
Sc["AnomalyScorer"]
P["AnomalyPolicyEngine"]
R["AnomalyRepo"]
DB["Models<br/>MarketAnomaly, MarketStructureSnapshot"]
S --> D1
S --> D2
S --> D3
S --> D4
S --> D5
S --> D6
S --> D7
S --> D8
S --> D9
S --> D10
S --> Sc
S --> P
S --> R
R --> DB
```

**Diagram sources**
- [src/apps/anomalies/services/anomaly_service.py:44-78](file://src/apps/anomalies/services/anomaly_service.py#L44-L78)
- [src/apps/anomalies/scoring/anomaly_scorer.py:13-38](file://src/apps/anomalies/scoring/anomaly_scorer.py#L13-L38)
- [src/apps/anomalies/policies.py:24-83](file://src/apps/anomalies/policies.py#L24-L83)
- [src/apps/anomalies/models.py:15-121](file://src/apps/anomalies/models.py#L15-L121)

**Section sources**
- [src/apps/anomalies/detectors/__init__.py:1-28](file://src/apps/anomalies/detectors/__init__.py#L1-L28)
- [src/apps/anomalies/services/anomaly_service.py:44-78](file://src/apps/anomalies/services/anomaly_service.py#L44-L78)
- [src/apps/anomalies/models.py:15-121](file://src/apps/anomalies/models.py#L15-L121)

## Core Components
- Detectors: Individual anomaly detection algorithms, each returning a standardized finding with anomaly type, component scores, metrics, confidence, and optional confirmation requirements.
- AnomalyScorer: Aggregates component scores using detector-specific weights into a normalized anomaly score, severity banding, and adjusted confidence.
- AnomalyPolicyEngine: Applies thresholds and regime multipliers to decide whether to skip, keep, refresh, transition, or create anomalies; manages cooldown windows and confirmation gating.
- AnomalyService: Orchestrates detection passes (fast-path, sector synchrony, market structure), runs scoring and policy, persists anomalies, enriches payloads, and publishes alerts.
- Persistence Models: SQLAlchemy models for anomalies and venue-market structure snapshots used by detectors requiring multi-venue/multi-symbol context.

**Section sources**
- [src/apps/anomalies/scoring/anomaly_scorer.py:13-38](file://src/apps/anomalies/scoring/anomaly_scorer.py#L13-L38)
- [src/apps/anomalies/policies.py:24-83](file://src/apps/anomalies/policies.py#L24-L83)
- [src/apps/anomalies/services/anomaly_service.py:44-410](file://src/apps/anomalies/services/anomaly_service.py#L44-L410)
- [src/apps/anomalies/models.py:15-121](file://src/apps/anomalies/models.py#L15-L121)

## Architecture Overview
The system operates in three detection passes:
- Fast Path: Real-time detection on newly closed candles using price/volume/spike/volatility/breakout/divergence/relative divergence/compression/expansion detectors.
- Sector Scan: Detects synchronized moves across sector peers and optionally triggers market structure scans.
- Market Structure Scan: Uses venue snapshots to detect cross-exchange dislocations and derivatives anomalies.

```mermaid
sequenceDiagram
participant Producer as "Candle Producer"
participant Service as "AnomalyService"
participant Repo as "AnomalyRepo"
participant Det as "Detectors"
participant Scorer as "AnomalyScorer"
participant Policy as "AnomalyPolicyEngine"
participant DB as "Database"
participant Stream as "Event Stream"
Producer->>Service : candle_closed(coin_id,timeframe,timestamp,source)
Service->>Repo : load_fast_detection_context(...)
Service->>Det : detect(context) for each fast detector
Det-->>Service : DetectorFinding[]
Service->>Scorer : score(finding)
Scorer-->>Service : (score, severity, confidence)
Service->>Policy : evaluate(type,score,regime,latest,confirm)
Policy-->>Service : decision(action,status,cooldown)
alt create/refresh/transition
Service->>Repo : persist/update anomaly
Repo->>DB : commit
Service->>Stream : publish event
else skip/keep
Service-->>Producer : no-op
end
```

**Diagram sources**
- [src/apps/anomalies/services/anomaly_service.py:80-111](file://src/apps/anomalies/services/anomaly_service.py#L80-L111)
- [src/apps/anomalies/services/anomaly_service.py:243-340](file://src/apps/anomalies/services/anomaly_service.py#L243-L340)
- [src/apps/anomalies/scoring/anomaly_scorer.py:23-38](file://src/apps/anomalies/scoring/anomaly_scorer.py#L23-L38)
- [src/apps/anomalies/policies.py:39-83](file://src/apps/anomalies/policies.py#L39-L83)

## Detailed Component Analysis

### Compression/Expansion Detection
Measures volatility compression followed by an abrupt expansion, validating squeeze strength and price jump intensity. Returns component scores for volatility and price, plus confidence and metrics capturing compression ratio, squeeze percentile, range expansion, and realized jump ratio.

```mermaid
flowchart TD
Start(["Detect Entry"]) --> Load["Load recent candles"]
Load --> CheckLen{"Enough history?"}
CheckLen --> |No| Exit["Return None"]
CheckLen --> |Yes| Compute["Compute returns, ATR, rolling std dev"]
Compute --> Ratios["Compute compression/expansion ratios"]
Ratios --> Thresholds{"Pass thresholds?"}
Thresholds --> |No| Exit
Thresholds --> |Yes| Score["Aggregate components<br/>volatility, price"]
Score --> Find["Build DetectorFinding"]
Find --> End(["Return Finding"])
```

**Diagram sources**
- [src/apps/anomalies/detectors/compression_expansion_detector.py:72-135](file://src/apps/anomalies/detectors/compression_expansion_detector.py#L72-L135)

**Section sources**
- [src/apps/anomalies/detectors/compression_expansion_detector.py:67-135](file://src/apps/anomalies/detectors/compression_expansion_detector.py#L67-L135)

### Correlation Breakdown Detection
Identifies decoupling from benchmark via correlation drop, beta shift, residual variance expansion, and peer dispersion. Requires confirmation hits and marks isolation relative to peers and benchmark.

```mermaid
flowchart TD
Start(["Detect Entry"]) --> Bench{"Benchmark available?"}
Bench --> |No| Exit["Return None"]
Bench --> |Yes| Returns["Align coin/bench returns"]
Returns --> Windows["Split baseline vs recent windows"]
Windows --> Stats["Compute long/short correlations, beta, residuals"]
Stats --> Residuals["Residual std and floor"]
Residuals --> PeerDisp["Peer latest return dispersion"]
PeerDisp --> Thresholds{"Corr drop & residual variance ok?"}
Thresholds --> |No| Exit
Thresholds --> |Yes| Confirm["Count recent residual confirmations"]
Confirm --> Find["Build DetectorFinding<br/>requires_confirmation"]
Find --> End(["Return Finding"])
```

**Diagram sources**
- [src/apps/anomalies/detectors/correlation_breakdown_detector.py:75-182](file://src/apps/anomalies/detectors/correlation_breakdown_detector.py#L75-L182)

**Section sources**
- [src/apps/anomalies/detectors/correlation_breakdown_detector.py:70-182](file://src/apps/anomalies/detectors/correlation_breakdown_detector.py#L70-L182)

### Cross-Exchange Dislocation Detection
Aggregates venue snapshots by timestamp to compute venue spread percentage and basis dispersion, then evaluates z-scores and persistence duration to flag dislocations across multiple venues.

```mermaid
flowchart TD
Start(["Detect Entry"]) --> Aggregate["Aggregate venue snapshots by timestamp"]
Aggregate --> Enough{"Enough rows?"}
Enough --> |No| Exit["Return None"]
Enough --> |Yes| Baseline["Compute baseline spread/basis stats"]
Baseline --> Current["Compute current spread/basis and z-scores"]
Current --> Duration["Measure dislocation duration"]
Duration --> Thresholds{"Spread threshold & component score ok?"}
Thresholds --> |No| Exit
Thresholds --> |Yes| Find["Build DetectorFinding<br/>affected_symbols=venues"]
Find --> End(["Return Finding"])
```

**Diagram sources**
- [src/apps/anomalies/detectors/cross_exchange_dislocation_detector.py:76-151](file://src/apps/anomalies/detectors/cross_exchange_dislocation_detector.py#L76-L151)

**Section sources**
- [src/apps/anomalies/detectors/cross_exchange_dislocation_detector.py:76-151](file://src/apps/anomalies/detectors/cross_exchange_dislocation_detector.py#L76-L151)

### Failed Breakout Detection
Captures breakouts that fail to sustain, measuring excursion beyond a recent range and rejection depth, while incorporating wick/body ratio and volume confirmation.

```mermaid
flowchart TD
Start(["Detect Entry"]) --> Load["Load candles and compute highs/lows/close"]
Load --> Range["Compute reference high/low over window"]
Range --> Excursions["Compute upside/downside excursions and rejections"]
Excursions --> Direction{"Any valid breakout?"}
Direction --> |No| Exit["Return None"]
Direction --> |Yes| Confirm["Compute volume ratio and wick/body ratio"]
Confirm --> Thresholds{"Component score meets threshold?"}
Thresholds --> |No| Exit
Thresholds --> |Yes| Find["Build DetectorFinding"]
Find --> End(["Return Finding"])
```

**Diagram sources**
- [src/apps/anomalies/detectors/failed_breakout_detector.py:38-123](file://src/apps/anomalies/detectors/failed_breakout_detector.py#L38-L123)

**Section sources**
- [src/apps/anomalies/detectors/failed_breakout_detector.py:33-123](file://src/apps/anomalies/detectors/failed_breakout_detector.py#L33-L123)

### Funding/Open Interest Analysis
Evaluates abnormal shifts in derivatives positioning via funding z-score, open interest expansion, basis divergence, and price impact adjusted by OI.

```mermaid
flowchart TD
Start(["Detect Entry"]) --> Aggregate["Aggregate venue funding, OI, basis"]
Aggregate --> Enough{"Enough series?"}
Enough --> |No| Exit["Return None"]
Enough --> |Yes| Baseline["Compute baseline means/std devs"]
Baseline --> Current["Compute current funding/oi/basis and adjustments"]
Current --> Thresholds{"Components meet minimums?"}
Thresholds --> |No| Exit
Thresholds --> |Yes| Find["Build DetectorFinding"]
Find --> End(["Return Finding"])
```

**Diagram sources**
- [src/apps/anomalies/detectors/funding_open_interest_detector.py:62-134](file://src/apps/anomalies/detectors/funding_open_interest_detector.py#L62-L134)

**Section sources**
- [src/apps/anomalies/detectors/funding_open_interest_detector.py:58-134](file://src/apps/anomalies/detectors/funding_open_interest_detector.py#L58-L134)

### Liquidation Cascade Detection
Flags forced unwinds across venues indicated by spikes in total liquidations, open interest drops, price impulse alignment with directional liquidations, and confirmation gating.

```mermaid
flowchart TD
Start(["Detect Entry"]) --> Aggregate["Aggregate venue liquidations and OI"]
Aggregate --> Enough{"Enough series?"}
Enough --> |No| Exit["Return None"]
Enough --> |Yes| Baseline["Compute baseline stats and current measures"]
Baseline --> Impulse["Compute price impulse vs historical returns"]
Impulse --> Alignment["Compute directional liquidation imbalance"]
Alignment --> Thresholds{"Z-score, impulse, component score ok?"}
Thresholds --> |No| Exit
Thresholds --> |Yes| Confirm["Set confirmation hits/target"]
Confirm --> Find["Build DetectorFinding<br/>requires_confirmation"]
Find --> End(["Return Finding"])
```

**Diagram sources**
- [src/apps/anomalies/detectors/liquidation_cascade_detector.py:60-140](file://src/apps/anomalies/detectors/liquidation_cascade_detector.py#L60-L140)

**Section sources**
- [src/apps/anomalies/detectors/liquidation_cascade_detector.py:56-140](file://src/apps/anomalies/detectors/liquidation_cascade_detector.py#L56-L140)

### Price Spike Detection
Scores abnormal price displacement using return z-score, percentile rank, candle range z-score, and ATR ratio against rolling baselines.

```mermaid
flowchart TD
Start(["Detect Entry"]) --> Load["Load candles"]
Load --> Enough{"Enough history?"}
Enough --> |No| Exit["Return None"]
Enough --> |Yes| Returns["Compute returns and baseline stats"]
Returns --> Range["Compute range ratios and ATR"]
Range --> Components["Compute z-score, percentile, range z, ATR ratio components"]
Components --> Thresholds{"Component score ok?"}
Thresholds --> |No| Exit
Thresholds --> |Yes| Find["Build DetectorFinding"]
Find --> End(["Return Finding"])
```

**Diagram sources**
- [src/apps/anomalies/detectors/price_spike_detector.py:74-138](file://src/apps/anomalies/detectors/price_spike_detector.py#L74-L138)

**Section sources**
- [src/apps/anomalies/detectors/price_spike_detector.py:70-138](file://src/apps/anomalies/detectors/price_spike_detector.py#L70-L138)

### Price-Volume Divergence Detection
Identifies situations where price moves strongly without volume participation (or vice versa), computing z-scores and ratios to quantify divergence modes.

```mermaid
flowchart TD
Start(["Detect Entry"]) --> Load["Load candles and volumes"]
Load --> Enough{"Enough data?"}
Enough --> |No| Exit["Return None"]
Enough --> |Yes| PriceVol["Compute price z-score and volume z/ratio"]
PriceVol --> Mode{"Mode identified?<br/>price-led or high-effort"}
Mode --> |No| Exit
Mode --> |Yes| Divergence["Compute divergence component and metrics"]
Divergence --> Thresholds{"Component score ok?"}
Thresholds --> |No| Exit
Thresholds --> |Yes| Find["Build DetectorFinding"]
Find --> End(["Return Finding"])
```

**Diagram sources**
- [src/apps/anomalies/detectors/price_volume_divergence_detector.py:45-131](file://src/apps/anomalies/detectors/price_volume_divergence_detector.py#L45-L131)

**Section sources**
- [src/apps/anomalies/detectors/price_volume_divergence_detector.py:41-131](file://src/apps/anomalies/detectors/price_volume_divergence_detector.py#L41-L131)

### Relative Divergence Detection
Computes beta-adjusted residuals relative to a benchmark and peers, scoring residual deviation, sector gap, and related gap, with confirmation gating and isolation determination.

```mermaid
flowchart TD
Start(["Detect Entry"]) --> Bench{"Benchmark available?"}
Bench --> |No| Exit["Return None"]
Bench --> Align["Align coin/bench returns"]
Align --> Residuals["Compute beta and residuals"]
Residuals --> Peers["Compute sector/related gaps"]
Peers --> Components["Compute residual, sector, related components"]
Components --> Confirm["Compute confirmation hits"]
Confirm --> Thresholds{"Component score ok?"}
Thresholds --> |No| Exit
Thresholds --> |Yes| Find["Build DetectorFinding<br/>requires_confirmation"]
Find --> End(["Return Finding"])
```

**Diagram sources**
- [src/apps/anomalies/detectors/relative_divergence_detector.py:59-147](file://src/apps/anomalies/detectors/relative_divergence_detector.py#L59-L147)

**Section sources**
- [src/apps/anomalies/detectors/relative_divergence_detector.py:55-147](file://src/apps/anomalies/detectors/relative_divergence_detector.py#L55-L147)

### Synchronous Move Detection
Scans sector peers for simultaneous abnormal returns, measuring breadth, intensity, and alignment to detect coordinated sector moves.

```mermaid
flowchart TD
Start(["Detect Entry"]) --> Peers{"Sector peers available?"}
Peers --> |No| Exit["Return None"]
Peers --> Zscores["Compute peer z-scores and signs"]
Zscores --> Filter["Filter z-scores >= threshold"]
Filter --> Metrics["Compute breadth, intensity, alignment"]
Metrics --> Thresholds{"Component score ok?"}
Thresholds --> |No| Exit
Thresholds --> |Yes| Find["Build DetectorFinding<br/>scope=sector, market_wide=true"]
Find --> End(["Return Finding"])
```

**Diagram sources**
- [src/apps/anomalies/detectors/synchronous_move_detector.py:44-121](file://src/apps/anomalies/detectors/synchronous_move_detector.py#L44-L121)

**Section sources**
- [src/apps/anomalies/detectors/synchronous_move_detector.py:40-121](file://src/apps/anomalies/detectors/synchronous_move_detector.py#L40-L121)

### Anomaly Scoring Methodology
The scorer computes a weighted average of active detector components, clamps to [0,1], and derives severity from predefined bands. Confidence is a mixture of weighted score and raw finding confidence, with small reductions for non-isolated anomalies.

```mermaid
flowchart TD
Start(["Score Entry"]) --> Active["Select components with positive weights and values"]
Active --> Weights["Sum active weights"]
Weights --> Weighted["Sum(weighted_component_score)"]
Weighted --> Score["weighted_score = weighted/sum(active_weights)"]
Score --> Severity["Map score to severity band"]
Severity --> Confidence["Compute confidence blend"]
Confidence --> Output["Return (score, severity, confidence)"]
```

**Diagram sources**
- [src/apps/anomalies/scoring/anomaly_scorer.py:23-38](file://src/apps/anomalies/scoring/anomaly_scorer.py#L23-L38)

**Section sources**
- [src/apps/anomalies/scoring/anomaly_scorer.py:13-38](file://src/apps/anomalies/scoring/anomaly_scorer.py#L13-L38)

### Severity Classification
Severity bands map numeric anomaly scores to discrete categories. The scorer iterates through bands and assigns the lowest band meeting the score threshold.

```mermaid
flowchart TD
Start(["Severity Entry"]) --> Loop["For each (band, lower_bound) in bands"]
Loop --> Check{"score >= lower_bound?"}
Check --> |Yes| Assign["Return band"]
Check --> |No| Next["Next band"]
Next --> Loop
Loop --> |Exhausted| Low["Return 'low'"]
```

**Diagram sources**
- [src/apps/anomalies/scoring/anomaly_scorer.py:17-21](file://src/apps/anomalies/scoring/anomaly_scorer.py#L17-L21)

**Section sources**
- [src/apps/anomalies/scoring/anomaly_scorer.py:17-21](file://src/apps/anomalies/scoring/anomaly_scorer.py#L17-L21)

### Alert Generation Workflow
On successful creation or refresh/transition, the service builds an AnomalyDraft, persists it, updates payload_json with enriched context/explainability, and publishes an event to the stream. Commit occurs only when changes are made.

```mermaid
sequenceDiagram
participant Service as "AnomalyService"
participant Repo as "AnomalyRepo"
participant Draft as "AnomalyDraft"
participant DB as "Database"
participant Stream as "Event Stream"
Service->>Repo : get_latest_open_for_update(...)
Service->>Service : build draft (score, severity, confidence, payload)
alt create
Service->>Repo : create_anomaly(draft)
Repo->>DB : insert
Service->>Stream : publish_event(ANOMALY_EVENT_TYPE, payload)
else refresh/transition
Service->>Repo : touch_anomaly(update fields)
Repo->>DB : update
end
Service->>Service : commit if changed
```

**Diagram sources**
- [src/apps/anomalies/services/anomaly_service.py:243-340](file://src/apps/anomalies/services/anomaly_service.py#L243-L340)

**Section sources**
- [src/apps/anomalies/services/anomaly_service.py:243-340](file://src/apps/anomalies/services/anomaly_service.py#L243-L340)

### Policy-Based Filtering
The policy engine defines entry/exit thresholds per anomaly type, adjusted by market regime multipliers, enforces confirmation targets, and manages cooldown windows. Decisions include skip, keep, refresh, transition, or create.

```mermaid
flowchart TD
Start(["Evaluate Entry"]) --> Confirm{"confirmation_hits >= target?"}
Confirm --> |No| Skip["Skip: awaiting_confirmation"]
Confirm --> |Yes| HasLatest{"Has open anomaly?"}
HasLatest --> |Yes| BelowExit{"score < exit_threshold?"}
BelowExit --> |Yes| Transition["Transition to cooling/resolved"]
BelowExit --> |No| AboveEntry{"score >= entry_threshold?"}
AboveEntry --> |Yes| Cooldown{"Within cooldown?"}
Cooldown --> |Yes| Refresh["Refresh existing"]
Cooldown --> |No| CreateNew["Create new"]
AboveEntry --> |No| Keep["Keep existing status"]
HasLatest --> |No| BelowEntry2{"score < entry_threshold?"}
BelowEntry2 --> |Yes| Skip2["Skip: below entry threshold"]
BelowEntry2 --> |No| CreateNew2["Create new"]
```

**Diagram sources**
- [src/apps/anomalies/policies.py:39-83](file://src/apps/anomalies/policies.py#L39-L83)

**Section sources**
- [src/apps/anomalies/policies.py:24-83](file://src/apps/anomalies/policies.py#L24-L83)

### Real-Time Monitoring and Historical Analysis
- Real-time: Fast-path detection on candle_closed events, with sector and market structure scans triggered by downstream logic.
- Historical: Persistence enables backtesting and analysis of past anomalies; sector synchronicity and market structure scans operate over configurable lookbacks.

**Section sources**
- [src/apps/anomalies/services/anomaly_service.py:80-191](file://src/apps/anomalies/services/anomaly_service.py#L80-L191)
- [src/apps/anomalies/models.py:15-62](file://src/apps/anomalies/models.py#L15-L62)

### Anomaly Enrichment
Enrichment augments anomaly payloads with portfolio relevance, market scope (isolated vs market-wide), and explainability metadata, then persists the updated payload.

```mermaid
flowchart TD
Start(["Enrich Entry"]) --> Load["Load anomaly for update"]
Load --> Context["Compute portfolio_relevant and sector_active_count"]
Context --> Scope["Derive market_wide and scope"]
Scope --> Payload["Update payload_json.context/explainability"]
Payload --> Persist["touch_anomaly(status,payload)"]
Persist --> Done(["Return enriched result"])
```

**Diagram sources**
- [src/apps/anomalies/services/anomaly_service.py:193-241](file://src/apps/anomalies/services/anomaly_service.py#L193-L241)

**Section sources**
- [src/apps/anomalies/services/anomaly_service.py:193-241](file://src/apps/anomalies/services/anomaly_service.py#L193-L241)

## Dependency Analysis
The system exhibits clear layering:
- Detectors depend on shared schemas and constants.
- Service composes detectors, scorer, and policy engine.
- Persistence models underpin repository operations used by the service.
- Event publishing is decoupled from service I/O via a stream abstraction.

```mermaid
graph LR
Det["Detectors"] --> Svc["AnomalyService"]
Scorer["AnomalyScorer"] --> Svc
Policy["AnomalyPolicyEngine"] --> Svc
Svc --> Repo["AnomalyRepo"]
Repo --> Models["Models"]
Svc --> Stream["Event Stream"]
```

**Diagram sources**
- [src/apps/anomalies/services/anomaly_service.py:21-41](file://src/apps/anomalies/services/anomaly_service.py#L21-L41)
- [src/apps/anomalies/models.py:15-62](file://src/apps/anomalies/models.py#L15-L62)

**Section sources**
- [src/apps/anomalies/services/anomaly_service.py:21-41](file://src/apps/anomalies/services/anomaly_service.py#L21-L41)
- [src/apps/anomalies/models.py:15-62](file://src/apps/anomalies/models.py#L15-L62)

## Performance Considerations
- Window sizing: Detectors specify minimal lookback windows; ensure adequate history availability to avoid frequent early exits.
- Rolling computations: Standard deviations and percentiles are computed per window; consider caching or streaming rolling aggregates if latency becomes a concern.
- Confirmation gating: Some detectors require confirmation hits; tune thresholds and targets to balance sensitivity and false positives.
- Streaming I/O: Event publishing uses a synchronous enqueue API backed by a dedicated thread; service remains non-blocking for the event loop.

## Troubleshooting Guide
- No anomalies created:
  - Verify detection context availability and sufficient lookback windows.
  - Check policy thresholds and market regime multipliers.
  - Confirm detector-specific thresholds are met.
- Excessive cooldown:
  - Review cooldown minutes per anomaly type and recent anomaly timing.
- Insufficient sector or venue data:
  - Ensure sector peer lists and venue snapshots are populated for relevant scans.
- Payload enrichment missing context:
  - Confirm sector anomaly counts and portfolio positions are available.

**Section sources**
- [src/apps/anomalies/services/anomaly_service.py:80-191](file://src/apps/anomalies/services/anomaly_service.py#L80-L191)
- [src/apps/anomalies/policies.py:36-37](file://src/apps/anomalies/policies.py#L36-L37)

## Conclusion
The anomaly detection system combines modular detectors, robust scoring, and policy-driven lifecycle management to deliver timely, interpretable alerts. Its layered design supports real-time monitoring, historical analysis, and enrichment for actionable insights across price, volume, volatility, correlation, derivatives, venue, and sector dynamics.

## Appendices
- Data Models: MarketAnomaly and MarketStructureSnapshot define persistence for anomalies and venue-market structure snapshots.
- Constants and Schemas: Shared anomaly types, severity bands, thresholds, and detection context structures are referenced by detectors and service.

**Section sources**
- [src/apps/anomalies/models.py:15-121](file://src/apps/anomalies/models.py#L15-L121)