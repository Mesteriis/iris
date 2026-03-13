# Signal Fusion Algorithms

<cite>
**Referenced Files in This Document**
- [fusion.py](file://src/apps/signals/fusion.py)
- [fusion_support.py](file://src/apps/signals/fusion_support.py)
- [services.py](file://src/apps/signals/services.py)
- [models.py](file://src/apps/signals/models.py)
- [semantics.py](file://src/apps/patterns/domain/semantics.py)
- [engine.py](file://src/apps/cross_market/engine.py)
- [anomaly_scorer.py](file://src/apps/anomalies/scoring/anomaly_scorer.py)
- [final_signal_selectors.py](file://src/apps/signals/final_signal_selectors.py)
- [history.py](file://src/apps/signals/history.py)
- [test_conflict.py](file://tests/apps/signals/test_conflict.py)
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

## Introduction
This document explains the signal fusion algorithms that combine multi-source signals (patterns, anomalies, indicators, and news) into coherent market decisions. It covers weighted averaging, voting systems, adaptive fusion, conflict resolution, priority scoring, and risk-adjusted signal generation. It also documents the mathematical foundations (probability, Bayesian-like weighting, and ensemble-style aggregation) and provides practical examples of how conflicting signals are resolved systematically.

## Project Structure
The signal fusion subsystem is centered around:
- Fusion orchestration and decision generation
- Support utilities for scoring, regime-aware weighting, and news impact
- Services that implement the fusion logic asynchronously
- Models representing signals, decisions, and risk metrics
- Cross-market alignment and sector trend integration
- Pattern semantics and anomaly scoring for heterogeneous sources

```mermaid
graph TB
subgraph "Signals Domain"
FUSION["fusion.py<br/>Decision orchestration"]
SUPP["fusion_support.py<br/>Scoring & regime helpers"]
SRV["services.py<br/>Async fusion service"]
MODELS["models.py<br/>Signal/Decision/Risk models"]
end
subgraph "Patterns"
SEM["semantics.py<br/>Pattern archetypes & bias"]
end
subgraph "Cross-Market"
CM["engine.py<br/>Alignment & sector trends"]
end
subgraph "Anomalies"
ANOM["anomaly_scorer.py<br/>Weighted anomaly scores"]
end
subgraph "Final Signals"
FINAL["final_signal_selectors.py<br/>Risk-adjusted signals"]
HIST["history.py<br/>Backtesting outcomes"]
end
FUSION --> SUPP
SRV --> FUSION
SRV --> SUPP
SRV --> CM
SRV --> SEM
SRV --> MODELS
FUSION --> CM
FUSION --> SEM
FUSION --> MODELS
FINAL --> MODELS
HIST --> MODELS
```

**Diagram sources**
- [fusion.py:1-457](file://src/apps/signals/fusion.py#L1-L457)
- [fusion_support.py:1-206](file://src/apps/signals/fusion_support.py#L1-L206)
- [services.py:1-849](file://src/apps/signals/services.py#L1-L849)
- [models.py:1-237](file://src/apps/signals/models.py#L1-L237)
- [semantics.py:1-134](file://src/apps/patterns/domain/semantics.py#L1-L134)
- [engine.py:1-495](file://src/apps/cross_market/engine.py#L1-L495)
- [anomaly_scorer.py:1-39](file://src/apps/anomalies/scoring/anomaly_scorer.py#L1-L39)
- [final_signal_selectors.py:1-281](file://src/apps/signals/final_signal_selectors.py#L1-L281)
- [history.py:1-270](file://src/apps/signals/history.py#L1-L270)

**Section sources**
- [fusion.py:1-457](file://src/apps/signals/fusion.py#L1-L457)
- [fusion_support.py:1-206](file://src/apps/signals/fusion_support.py#L1-L206)
- [services.py:1-849](file://src/apps/signals/services.py#L1-L849)
- [models.py:1-237](file://src/apps/signals/models.py#L1-L237)
- [semantics.py:1-134](file://src/apps/patterns/domain/semantics.py#L1-L134)
- [engine.py:1-495](file://src/apps/cross_market/engine.py#L1-L495)
- [anomaly_scorer.py:1-39](file://src/apps/anomalies/scoring/anomaly_scorer.py#L1-L39)
- [final_signal_selectors.py:1-281](file://src/apps/signals/final_signal_selectors.py#L1-L281)
- [history.py:1-270](file://src/apps/signals/history.py#L1-L270)

## Core Components
- Weighted signal scoring: combines confidence, success rate, context, regime alignment, priority, recency, and cross-market alignment into a per-signal score.
- Ensemble-style fusion: sums bullish/bearish weighted scores, derives decision via dominance/agreement thresholds, and computes confidence.
- News impact fusion: aggregates sentiment-weighted news items into bullish/bearish scores and re-computes decision/confidence.
- Adaptive regime weighting: adjusts signal weights depending on detected market regime and pattern archetype.
- Conflict resolution: when opposing signals are strong and balanced, decision may default to HOLD or WATCH based on thresholds.
- Risk-adjusted final signals: produce a final recommendation incorporating liquidity, slippage, and volatility risks.

Key parameters and limits:
- Signal windowing: up to a fixed number of candle groups and recent signals.
- News window: timeframe-dependent lookback with capped items and score.
- Materiality thresholds: minimum total score and confidence delta to emit changes.

**Section sources**
- [fusion.py:50-125](file://src/apps/signals/fusion.py#L50-L125)
- [fusion_support.py:11-17](file://src/apps/signals/fusion_support.py#L11-L17)
- [services.py:575-645](file://src/apps/signals/services.py#L575-L645)

## Architecture Overview
The fusion pipeline integrates multiple sources and applies adaptive weighting and conflict resolution.

```mermaid
sequenceDiagram
participant Trigger as "Trigger"
participant Service as "SignalFusionService"
participant Repo as "SignalFusionRepository"
participant DB as "Database"
participant Patterns as "Pattern Semantics"
participant Cross as "Cross-Market Engine"
participant Fusion as "Fusion Core"
Trigger->>Service : evaluate_market_decision(coin_id, timeframe, ...)
Service->>Repo : list candidate timeframes
Service->>Repo : list recent signals (windowed)
Service->>DB : load CoinMetrics, PatternStatistics
Service->>Patterns : compute success rates, archetypes, bias
Service->>Cross : cross-market alignment weights
Service->>Fusion : fuse_signals + decision_from_scores
Fusion-->>Service : FusionSnapshot
Service->>DB : persist MarketDecision
Service-->>Trigger : SignalFusionResult
```

**Diagram sources**
- [services.py:235-417](file://src/apps/signals/services.py#L235-L417)
- [fusion.py:290-322](file://src/apps/signals/fusion.py#L290-L322)
- [semantics.py:106-134](file://src/apps/patterns/domain/semantics.py#L106-L134)
- [engine.py:446-494](file://src/apps/cross_market/engine.py#L446-L494)

## Detailed Component Analysis

### Weighted Signal Scoring and Ensemble Fusion
- Inputs per signal:
  - Confidence: raw signal strength
  - Success rate: historical pattern accuracy by regime
  - Context factor: contextual score
  - Regime alignment: alignment with detected regime
  - Priority factor: explicit priority vs confidence
  - Directional bias: derived from pattern slug or price delta
  - Cross-market factor: alignment with leaders/sector
  - Recency weight: decays older signals
- Aggregation:
  - Sum bullish and bearish weighted scores
  - Decision derived from dominance/agreement thresholds
  - Confidence computed from dominance and totals

```mermaid
flowchart TD
Start(["Start fusion"]) --> Load["Load signals & regime"]
Load --> Group["Group by candle timestamp (window)"]
Group --> Loop{"For each signal"}
Loop --> Score["Compute weighted score<br/>confidence × sr × ctx × align × prio × bias × cm × recency"]
Score --> Split{"Bias > 0 ?"}
Split --> |Yes| Bull["Add to bullish score"]
Split --> |No| Bear["Add to bearish score"]
Bull --> Next[Loop]
Bear --> Next
Next --> Done{"More signals?"}
Done --> |Yes| Loop
Done --> |No| Aggregate["Sum bullish/bearish"]
Aggregate --> Decision["decision_from_scores(bull, bear, total)"]
Decision --> End(["Return FusionSnapshot"])
```

**Diagram sources**
- [fusion.py:209-241](file://src/apps/signals/fusion.py#L209-L241)
- [services.py:585-645](file://src/apps/signals/services.py#L585-L645)
- [fusion_support.py:146-157](file://src/apps/signals/fusion_support.py#L146-L157)

**Section sources**
- [fusion.py:97-125](file://src/apps/signals/fusion.py#L97-L125)
- [services.py:585-645](file://src/apps/signals/services.py#L585-L645)
- [fusion_support.py:146-157](file://src/apps/signals/fusion_support.py#L146-L157)

### Adaptive Regime Weighting and Cross-Market Alignment
- Regime weight depends on pattern archetype and detected regime.
- Cross-market alignment weight increases/decreases based on leading coins’ decisions and sector trend.

```mermaid
flowchart TD
A["Regime: bull/bear/sideways/high/low volatility"] --> B{"Archetype: continuation/reversal/breakout/mean_reversion"}
B --> C["Regime weight multiplier"]
D["Directional bias (+1/-1/0)"] --> E["Leader decisions & correlations"]
E --> F["Cross-market alignment weight"]
G["Sector trend"] --> H["Sector alignment boost/dampen"]
C --> I["Apply to signal score"]
F --> I
H --> I
```

**Diagram sources**
- [fusion_support.py:114-143](file://src/apps/signals/fusion_support.py#L114-L143)
- [engine.py:446-494](file://src/apps/cross_market/engine.py#L446-L494)

**Section sources**
- [fusion_support.py:114-143](file://src/apps/signals/fusion_support.py#L114-L143)
- [engine.py:446-494](file://src/apps/cross_market/engine.py#L446-L494)

### Conflict Resolution and Priority Scoring
- When both sides are strong and balanced, decision defaults to HOLD.
- WATCH is applied when total score is below threshold.
- Priority score and confidence are merged into a priority factor.

```mermaid
flowchart TD
S["Signal set"] --> T["Total directional score"]
T --> Th{"Total score < WATCH_MIN ?"}
Th --> |Yes| Watch["Decision=WATCH, confidence≈0.2"]
Th --> |No| Dom["Dominance = |bull-bear|/(bull+bear)"]
Dom --> Bal{"Dominance < 0.2 and both>0 ?"}
Bal --> |Yes| Hold["Decision=HOLD, confidence from formula"]
Bal --> |No| Strong{"Bull > Bear ?"}
Strong --> |Yes| Buy["Decision=BUY, confidence from formula"]
Strong --> |No| Sell["Decision=SELL, confidence from formula"]
```

**Diagram sources**
- [fusion_support.py:146-157](file://src/apps/signals/fusion_support.py#L146-L157)

**Section sources**
- [fusion_support.py:146-157](file://src/apps/signals/fusion_support.py#L146-L157)
- [test_conflict.py:9-42](file://tests/apps/signals/test_conflict.py#L9-L42)

### News Impact Fusion
- Recent news items are scored by relevance, confidence, and recency.
- Sentiment is aggregated into bullish/bearish scores and capped.
- Fusion result is recomputed with combined scores.

```mermaid
sequenceDiagram
participant Service as "SignalFusionService"
participant DB as "Database"
participant News as "News Impact"
participant Fusion as "Fusion Core"
Service->>DB : list recent normalized news
DB-->>Service : rows (item, relevance, sentiment, confidence, published_at)
Service->>News : compute recency weights, cap scores
News-->>Service : bullish_score, bearish_score
Service->>Fusion : _apply_news_impact(fused, impact)
Fusion-->>Service : new FusionSnapshot
```

**Diagram sources**
- [services.py:530-573](file://src/apps/signals/services.py#L530-L573)
- [fusion.py:138-196](file://src/apps/signals/fusion.py#L138-L196)
- [fusion_support.py:160-187](file://src/apps/signals/fusion_support.py#L160-L187)

**Section sources**
- [services.py:530-573](file://src/apps/signals/services.py#L530-L573)
- [fusion.py:138-196](file://src/apps/signals/fusion.py#L138-L196)
- [fusion_support.py:160-187](file://src/apps/signals/fusion_support.py#L160-L187)

### Risk-Adjusted Signal Generation
- Final signals incorporate risk metrics (liquidity, slippage, volatility) and a risk-adjusted score.
- Decisions are canonicalized across timeframes and enriched with sector and reason metadata.

```mermaid
classDiagram
class RiskMetric {
+coin_id
+timeframe
+liquidity_score
+slippage_risk
+volatility_risk
}
class FinalSignal {
+decision
+confidence
+risk_adjusted_score
+reason
}
RiskMetric <.. FinalSignal : "joined for final signal"
```

**Diagram sources**
- [models.py:151-165](file://src/apps/signals/models.py#L151-L165)
- [models.py:83-103](file://src/apps/signals/models.py#L83-L103)
- [final_signal_selectors.py:46-76](file://src/apps/signals/final_signal_selectors.py#L46-L76)

**Section sources**
- [models.py:151-165](file://src/apps/signals/models.py#L151-L165)
- [models.py:83-103](file://src/apps/signals/models.py#L83-L103)
- [final_signal_selectors.py:46-76](file://src/apps/signals/final_signal_selectors.py#L46-L76)

### Mathematical Foundations
- Weighted averaging: each signal contributes a score proportional to confidence and derived weights.
- Voting system: bullish/bearish sides compete; dominance/agreement thresholds decide outcome.
- Adaptive fusion: regime/archetype-aware weights and cross-market alignment dynamically adjust influence.
- Risk-adjusted generation: final recommendation balances expected return against risk metrics.

**Section sources**
- [fusion.py:209-241](file://src/apps/signals/fusion.py#L209-L241)
- [services.py:585-645](file://src/apps/signals/services.py#L585-L645)
- [fusion_support.py:146-157](file://src/apps/signals/fusion_support.py#L146-L157)

### Implementation of Different Fusion Strategies
- Pattern signals: derive bias and success rate from pattern slug; regime/archetype weighting applied.
- Anomaly signals: weighted anomaly scoring (detector weights, severity bands, confidence blending).
- Indicator signals: context scores, regime alignment, and priority scores integrated.
- News signals: sentiment-relevance-confidence-weighted aggregation.

Parameters and characteristics:
- Windowing: bounded by candle groups and signal count.
- Lookbacks: news lookback varies by timeframe.
- Clamping: all weights and scores constrained to safe ranges.
- Materiality: minimal confidence delta determines emission of unchanged decisions.

**Section sources**
- [fusion.py:50-68](file://src/apps/signals/fusion.py#L50-L68)
- [services.py:443-460](file://src/apps/signals/services.py#L443-L460)
- [anomaly_scorer.py:23-38](file://src/apps/anomalies/scoring/anomaly_scorer.py#L23-L38)

### Practical Examples of Signal Combinations
- Example: Conflicting pattern signals (e.g., breakout and reversal) at the same candle timestamp lead to balanced scores and a HOLD decision when dominance is low.
- Example: Mixed bullish/bearish pattern signals with moderate total score yield WATCH until sufficient conviction builds.
- Example: Strong cross-market alignment boosts signal weights, shifting decision toward consensus.

Validation:
- Unit test demonstrates conflicting stack resolves to HOLD with material confidence.

**Section sources**
- [test_conflict.py:9-42](file://tests/apps/signals/test_conflict.py#L9-L42)

## Dependency Analysis
- Fusion core depends on:
  - Pattern semantics for slug-to-bias mapping and archetypes
  - Cross-market engine for leader/sector alignment weights
  - Models for signals, decisions, and risk metrics
  - Services for asynchronous orchestration and repository access

```mermaid
graph LR
F["fusion.py"] --> S["services.py"]
F --> U["fusion_support.py"]
F --> M["models.py"]
F --> P["patterns.semantics"]
F --> C["cross_market.engine"]
S --> U
S --> P
S --> C
S --> M
```

**Diagram sources**
- [fusion.py:1-457](file://src/apps/signals/fusion.py#L1-L457)
- [services.py:1-849](file://src/apps/signals/services.py#L1-L849)
- [fusion_support.py:1-206](file://src/apps/signals/fusion_support.py#L1-L206)
- [models.py:1-237](file://src/apps/signals/models.py#L1-L237)
- [semantics.py:1-134](file://src/apps/patterns/domain/semantics.py#L1-L134)
- [engine.py:1-495](file://src/apps/cross_market/engine.py#L1-L495)

**Section sources**
- [fusion.py:1-457](file://src/apps/signals/fusion.py#L1-L457)
- [services.py:1-849](file://src/apps/signals/services.py#L1-L849)
- [fusion_support.py:1-206](file://src/apps/signals/fusion_support.py#L1-L206)
- [models.py:1-237](file://src/apps/signals/models.py#L1-L237)
- [semantics.py:1-134](file://src/apps/patterns/domain/semantics.py#L1-L134)
- [engine.py:1-495](file://src/apps/cross_market/engine.py#L1-L495)

## Performance Considerations
- Windowing reduces computational load by limiting recent candles and signal counts.
- Asynchronous service minimizes latency in production environments.
- Clamping avoids extreme weights and stabilizes numerical behavior.
- Caching of cross-market correlations reduces repeated heavy computations.

## Troubleshooting Guide
Common issues and resolutions:
- No signals found: fusion skips and returns appropriate reason.
- Unchanged decision: if decision, signal count, and confidence change below material delta, skip emission and cache latest.
- Insufficient news: if no normalized news items, news impact is ignored.
- Pattern statistics missing: fallback success rates applied for cluster/hierarchy and generic patterns.

Operational logs:
- Compatibility shims log deprecated calls with mode and reasons.
- Service logs debug/info for skipped/ok results and emitted events.

**Section sources**
- [fusion.py:306-350](file://src/apps/signals/fusion.py#L306-L350)
- [services.py:256-355](file://src/apps/signals/services.py#L256-L355)
- [history.py:82-186](file://src/apps/signals/history.py#L82-L186)

## Conclusion
The signal fusion system combines heterogeneous sources using weighted averaging and ensemble-style decision-making, with adaptive regime and cross-market adjustments. Conflict resolution favors HOLD when signals are evenly matched, and risk-adjusted final signals incorporate liquidity and volatility. Parameters and thresholds ensure robustness and stability across varying market conditions.