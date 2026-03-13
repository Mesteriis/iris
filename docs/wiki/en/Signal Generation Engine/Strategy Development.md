# Strategy Development

<cite>
**Referenced Files in This Document**
- [strategy.py](file://src/apps/patterns/domain/strategy.py)
- [models.py](file://src/apps/signals/models.py)
- [strategies.py](file://src/apps/signals/strategies.py)
- [task_services.py](file://src/apps/patterns/task_services.py)
- [evaluation.py](file://src/apps/patterns/domain/evaluation.py)
- [regime.py](file://src/apps/patterns/domain/regime.py)
- [cycle.py](file://src/apps/patterns/domain/cycle.py)
- [task_service_market.py](file://src/apps/patterns/task_service_market.py)
- [fusion.py](file://src/apps/signals/fusion.py)
- [risk.py](file://src/apps/patterns/domain/risk.py)
- [statistics.py](file://src/apps/patterns/domain/statistics.py)
- [success.py](file://src/apps/patterns/domain/success.py)
- [models.py](file://src/apps/patterns/models.py)
- [backtests.py](file://src/apps/signals/backtests.py)
- [backtest_support.py](file://src/apps/signals/backtest_support.py)
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
This document explains the strategy development and management framework implemented in the backend. It covers the strategy definition model, rule-based pattern matching, regime and cycle adaptations, and sector-aware considerations. It documents the strategy performance tracking system (sample size, win rate, Sharpe ratio, maximum drawdown), lifecycle management (creation, testing, deployment, optimization), and integration with pattern recognition, signal evaluation, and risk-adjusted decision making. Practical examples and optimization techniques are included, along with benchmarking against market conditions.

## Project Structure
The strategy system spans several domains:
- Strategy discovery and maintenance: patterns domain and signals models
- Strategy evaluation and lifecycle: patterns domain and task services
- Pattern statistics and success lifecycle: patterns domain
- Risk-adjusted decision making: risk domain and signals models
- Backtesting and performance benchmarking: signals backtests and support utilities

```mermaid
graph TB
subgraph "Patterns Domain"
STRAT["Strategy Discovery<br/>strategy.py"]
EVAL["Evaluation Cycle<br/>evaluation.py"]
REGIME["Regime Detection<br/>regime.py"]
CYCLE["Cycle Phase Detection<br/>cycle.py"]
STAT["Pattern Statistics<br/>statistics.py"]
SUCCESS["Pattern Success Lifecycle<br/>success.py"]
end
subgraph "Signals Domain"
MODELS["Strategy Models<br/>signals models.py"]
FUSION["Signal Fusion & Context<br/>fusion.py"]
BACKTEST["Backtests & Metrics<br/>backtests.py / backtest_support.py"]
end
subgraph "Risk Domain"
RISK["Risk Metrics & Adjustment<br/>risk.py"]
end
subgraph "Task Services"
TS["Pattern Task Services<br/>task_services.py"]
TSMKT["Market Mixin<br/>task_service_market.py"]
end
STRAT --> MODELS
EVAL --> STRAT
EVAL --> STAT
EVAL --> FUSION
EVAL --> RISK
REGIME --> STRAT
CYCLE --> STRAT
STAT --> SUCCESS
FUSION --> STRAT
BACKTEST --> MODELS
RISK --> MODELS
TS --> EVAL
TS --> TSMKT
```

**Diagram sources**
- [strategy.py:334-441](file://src/apps/patterns/domain/strategy.py#L334-L441)
- [evaluation.py:12-26](file://src/apps/patterns/domain/evaluation.py#L12-L26)
- [regime.py:25-66](file://src/apps/patterns/domain/regime.py#L25-L66)
- [cycle.py:65-101](file://src/apps/patterns/domain/cycle.py#L65-L101)
- [statistics.py:101-276](file://src/apps/patterns/domain/statistics.py#L101-L276)
- [success.py:128-277](file://src/apps/patterns/domain/success.py#L128-L277)
- [models.py:168-236](file://src/apps/signals/models.py#L168-L236)
- [fusion.py:71-94](file://src/apps/signals/fusion.py#L71-L94)
- [backtests.py:26-271](file://src/apps/signals/backtests.py#L26-L271)
- [backtest_support.py:34-69](file://src/apps/signals/backtest_support.py#L34-L69)
- [risk.py:160-357](file://src/apps/patterns/domain/risk.py#L160-L357)
- [task_services.py:27-166](file://src/apps/patterns/task_services.py#L27-L166)
- [task_service_market.py:161-188](file://src/apps/patterns/task_service_market.py#L161-L188)

**Section sources**
- [strategy.py:1-491](file://src/apps/patterns/domain/strategy.py#L1-L491)
- [models.py:1-237](file://src/apps/signals/models.py#L1-L237)
- [task_services.py:1-166](file://src/apps/patterns/task_services.py#L1-L166)

## Core Components
- Strategy definition and discovery: automatic candidate generation from pattern signals, with regime, sector, and cycle filters; performance thresholds determine enablement; upsert maintains rules and performance metrics.
- Strategy evaluation cycle: orchestrated refresh of signal history, pattern statistics, contexts, investment decisions, and final signals.
- Pattern statistics and success lifecycle: rolling-window success rates, temperature-based lifecycle state, and event emission for lifecycle transitions.
- Risk-adjusted decision making: computes risk metrics and adjusts decision strength and confidence based on liquidity, slippage, and volatility risks.
- Backtesting and benchmarking: historical signal outcomes aggregated into performance summaries with Sharpe ratio and drawdown metrics.

Key implementation references:
- Strategy discovery and upsert: [strategy.py:334-441](file://src/apps/patterns/domain/strategy.py#L334-L441)
- Strategy alignment and filtering: [strategy.py:443-491](file://src/apps/patterns/domain/strategy.py#L443-L491)
- Evaluation cycle orchestration: [evaluation.py:12-26](file://src/apps/patterns/domain/evaluation.py#L12-L26)
- Pattern statistics and lifecycle: [statistics.py:101-276](file://src/apps/patterns/domain/statistics.py#L101-L276), [success.py:128-277](file://src/apps/patterns/domain/success.py#L128-L277)
- Risk metrics and adjustment: [risk.py:160-357](file://src/apps/patterns/domain/risk.py#L160-L357)
- Backtests and metrics: [backtests.py:26-271](file://src/apps/signals/backtests.py#L26-L271), [backtest_support.py:34-69](file://src/apps/signals/backtest_support.py#L34-L69)

**Section sources**
- [strategy.py:24-491](file://src/apps/patterns/domain/strategy.py#L24-L491)
- [evaluation.py:12-26](file://src/apps/patterns/domain/evaluation.py#L12-L26)
- [statistics.py:101-276](file://src/apps/patterns/domain/statistics.py#L101-L276)
- [success.py:128-277](file://src/apps/patterns/domain/success.py#L128-L277)
- [risk.py:160-357](file://src/apps/patterns/domain/risk.py#L160-L357)
- [backtests.py:26-271](file://src/apps/signals/backtests.py#L26-L271)
- [backtest_support.py:34-69](file://src/apps/signals/backtest_support.py#L34-L69)

## Architecture Overview
The strategy lifecycle integrates pattern recognition, market regime/cycle detection, and risk-aware decision making. The evaluation cycle ensures continuous updates to strategy performance and pattern success states.

```mermaid
sequenceDiagram
participant Orchestrator as "PatternEvaluationService<br/>task_services.py"
participant History as "Signal History Refresh<br/>evaluation.py"
participant Stats as "Pattern Statistics<br/>statistics.py"
participant Context as "Signal Context<br/>strategy.py"
participant Decisions as "Investment Decisions<br/>strategy.py"
participant Final as "Final Signals<br/>risk.py"
Orchestrator->>History : refresh_signal_history(lookback=365)
Orchestrator->>Stats : refresh_pattern_statistics()
Orchestrator->>Context : refresh_recent_signal_contexts(lookback=30)
Orchestrator->>Decisions : refresh_investment_decisions(lookback=30)
Orchestrator->>Final : refresh_final_signals(lookback=30)
Orchestrator-->>Orchestrator : return results
```

**Diagram sources**
- [task_services.py:27-46](file://src/apps/patterns/task_services.py#L27-L46)
- [evaluation.py:12-26](file://src/apps/patterns/domain/evaluation.py#L12-L26)
- [statistics.py:101-276](file://src/apps/patterns/domain/statistics.py#L101-L276)
- [strategy.py:101-127](file://src/apps/patterns/domain/strategy.py#L101-L127)
- [risk.py:335-357](file://src/apps/patterns/domain/risk.py#L335-L357)

## Detailed Component Analysis

### Strategy Definition Framework
- Candidate generation: builds StrategyCandidate instances from top-ranked pattern tokens, considering regime, sector, and cycle. Tokens are deduplicated and confidence is rounded to discrete buckets.
- Context inference: regime and cycle derived from recent indicators and sector metrics; trend score computed from price and moving averages.
- Outcome computation: terminal return and drawdown measured over a fixed horizon per timeframe; bias determined by weighted signal stack.
- Performance thresholds: sample size, win rate, average return, Sharpe ratio, and maximum drawdown gate whether a strategy is enabled.
- Upsert logic: creates or updates Strategy, StrategyRule entries, and StrategyPerformance; disables previously unseen strategies.

```mermaid
flowchart TD
Start(["Refresh Strategies"]) --> GroupSignals["Group Signals by Coin/Timeframe"]
GroupSignals --> BuildWindows["Build Indicator Windows<br/>and Sector Metrics"]
BuildWindows --> DetectRegimeCycle["Detect Regime & Cycle"]
DetectRegimeCycle --> DefineCandidates["Define Strategy Candidates<br/>(tokens x regime x sector x cycle)"]
DefineCandidates --> ComputeOutcomes["Compute Terminal Returns & Drawdowns"]
ComputeOutcomes --> AggregatePerf["Aggregate Sample Size, Win Rate,<br/>Avg Return, Sharpe Ratio, Max DD"]
AggregatePerf --> EnableGate{"Enabled by Thresholds?"}
EnableGate --> |Yes| Upsert["Upsert Strategy + Rules + Performance"]
EnableGate --> |No| Skip["Skip Strategy"]
Upsert --> End(["Done"])
Skip --> End
```

**Diagram sources**
- [strategy.py:334-441](file://src/apps/patterns/domain/strategy.py#L334-L441)
- [regime.py:25-66](file://src/apps/patterns/domain/regime.py#L25-L66)
- [cycle.py:65-101](file://src/apps/patterns/domain/cycle.py#L65-L101)

**Section sources**
- [strategy.py:193-441](file://src/apps/patterns/domain/strategy.py#L193-L441)
- [regime.py:25-66](file://src/apps/patterns/domain/regime.py#L25-L66)
- [cycle.py:65-101](file://src/apps/patterns/domain/cycle.py#L65-L101)

### Rule-Based Pattern Matching and Strategy Alignment
- Strategy rules define allowed pattern slugs with optional regime, sector, and cycle constraints and minimum confidence thresholds.
- Strategy alignment scores strategies by performance metrics and returns matched strategy names.

```mermaid
flowchart TD
A["Tokens + Confidences"] --> B["Load Enabled Strategies"]
B --> C{"Match Rules?<br/>slug ∈ tokens<br/>regime*, sector*, cycle*<br/>min confidence"}
C --> |No| D["Skip Strategy"]
C --> |Yes| E["Compute Alignment Score<br/>Win Rate × Sharpe × Avg Return × Penalty"]
D --> F["Next Strategy"]
E --> F
F --> G["Return Best Alignment + Top Matches"]
```

**Diagram sources**
- [strategy.py:443-491](file://src/apps/patterns/domain/strategy.py#L443-L491)
- [models.py:168-236](file://src/apps/signals/models.py#L168-L236)

**Section sources**
- [strategy.py:443-491](file://src/apps/patterns/domain/strategy.py#L443-L491)
- [models.py:195-236](file://src/apps/signals/models.py#L195-L236)

### Regime-Specific Adaptations and Sector/Cycle Considerations
- Regime detection uses trend, volatility, and channel expansion/contraction signals to label market conditions with confidence.
- Sector metrics augment context with sector strength and capital flow.
- Cycle phase inferred from trend score, volatility, price, pattern density, and cluster frequency; combined with regime and sector alignment.

```mermaid
flowchart TD
S["Recent Window + Signals"] --> I["Compute Indicators"]
I --> R["Detect Regime"]
I --> SM["Fetch Sector Metric"]
R --> CD["Compute Pattern Density & Cluster Frequency"]
CD --> CY["Detect Cycle Phase"]
SM --> CY
CY --> OUT["Regime + Cycle Labels"]
```

**Diagram sources**
- [regime.py:25-66](file://src/apps/patterns/domain/regime.py#L25-L66)
- [cycle.py:65-101](file://src/apps/patterns/domain/cycle.py#L65-L101)
- [task_service_market.py:161-188](file://src/apps/patterns/task_service_market.py#L161-L188)

**Section sources**
- [regime.py:25-66](file://src/apps/patterns/domain/regime.py#L25-L66)
- [cycle.py:65-101](file://src/apps/patterns/domain/cycle.py#L65-L101)
- [task_service_market.py:161-188](file://src/apps/patterns/task_service_market.py#L161-L188)

### Strategy Performance Tracking System
- Metrics tracked: sample size, win rate, average return, Sharpe ratio, maximum drawdown.
- Sharpe ratio computed from observed returns; thresholds enforce minimum viability.
- StrategyPerformance records are updated during strategy refresh.

```mermaid
flowchart TD
O["Observations per Candidate"] --> SS["Sample Size"]
O --> WR["Win Rate"]
O --> AR["Avg Return"]
O --> SR["Sharpe Ratio"]
O --> MD["Max Drawdown"]
SS --> Gate{"Meets Min Thresholds?"}
Gate --> |Yes| Enable["Enable Strategy"]
Gate --> |No| Disable["Disable Strategy"]
Enable --> Perf["Update Performance"]
Disable --> Perf
```

**Diagram sources**
- [strategy.py:388-414](file://src/apps/patterns/domain/strategy.py#L388-L414)
- [strategy.py:260-277](file://src/apps/patterns/domain/strategy.py#L260-L277)
- [models.py:208-223](file://src/apps/signals/models.py#L208-L223)

**Section sources**
- [strategy.py:260-277](file://src/apps/patterns/domain/strategy.py#L260-L277)
- [strategy.py:388-414](file://src/apps/patterns/domain/strategy.py#L388-L414)
- [models.py:208-223](file://src/apps/signals/models.py#L208-L223)

### Strategy Lifecycle Management
- Creation: automatic discovery and upsert of strategies from pattern signals.
- Testing: evaluation cycle runs history refresh, statistics refresh, context enrichment, decisions, and final signals.
- Deployment: strategies are enabled/disabled based on thresholds; only enabled strategies participate in alignment.
- Optimization: pattern success lifecycle adjusts confidence and emits lifecycle events; strategy alignment incorporates performance factors.

```mermaid
stateDiagram-v2
[*] --> Created
Created --> Enabled : "Meets thresholds"
Created --> Disabled : "Below thresholds"
Enabled --> Optimizing : "High Sharpe/Win Rate"
Optimizing --> Enabled : "Stable performance"
Enabled --> Disabled : "Performance drops"
Disabled --> Created : "Re-discovered"
```

**Diagram sources**
- [strategy.py:270-277](file://src/apps/patterns/domain/strategy.py#L270-L277)
- [success.py:128-277](file://src/apps/patterns/domain/success.py#L128-L277)
- [task_services.py:27-46](file://src/apps/patterns/task_services.py#L27-L46)

**Section sources**
- [strategy.py:270-277](file://src/apps/patterns/domain/strategy.py#L270-L277)
- [success.py:128-277](file://src/apps/patterns/domain/success.py#L128-L277)
- [task_services.py:27-46](file://src/apps/patterns/task_services.py#L27-L46)

### Integration with Pattern Recognition Results and Signal Evaluation
- Pattern statistics provide success rates and temperature used to adjust pattern confidence and lifecycle state.
- Fusion logic retrieves pattern success rates for signals and applies regime-aware adjustments.
- Strategy alignment considers pattern success actions and factors.

```mermaid
sequenceDiagram
participant Stat as "Pattern Statistics<br/>statistics.py"
participant Fuse as "Signal Fusion<br/>fusion.py"
participant Strat as "Strategy Alignment<br/>strategy.py"
Stat-->>Fuse : success_rate per slug/timeframe/regime
Fuse->>Strat : pattern_success_factor, success_rate
Strat-->>Strat : adjust alignment score
```

**Diagram sources**
- [statistics.py:101-276](file://src/apps/patterns/domain/statistics.py#L101-L276)
- [fusion.py:71-94](file://src/apps/signals/fusion.py#L71-L94)
- [strategy.py:443-491](file://src/apps/patterns/domain/strategy.py#L443-L491)

**Section sources**
- [statistics.py:101-276](file://src/apps/patterns/domain/statistics.py#L101-L276)
- [fusion.py:71-94](file://src/apps/signals/fusion.py#L71-L94)
- [strategy.py:443-491](file://src/apps/patterns/domain/strategy.py#L443-L491)

### Risk-Adjusted Decision Making
- Risk metrics computed from liquidity, slippage risk, and volatility risk.
- Final signal decision adjusted by risk-adjusted score; confidence scaled accordingly.
- Decision reasons captured for auditability.

```mermaid
flowchart TD
A["Latest Decision + Confidence"] --> B["Compute Risk Metrics"]
B --> C["Calculate Risk-Adjusted Score"]
C --> D{"Score Threshold?"}
D --> |Pass| E["Adjust Decision Strength"]
D --> |Fail| F["Hold"]
E --> G["Publish Final Signal"]
F --> G
```

**Diagram sources**
- [risk.py:235-322](file://src/apps/patterns/domain/risk.py#L235-L322)

**Section sources**
- [risk.py:160-357](file://src/apps/patterns/domain/risk.py#L160-L357)
- [models.py:83-127](file://src/apps/signals/models.py#L83-L127)

### Performance Benchmarking and Backtesting
- Historical outcomes aggregated per signal type and timeframe; Sharpe ratio and drawdown computed.
- Backtests expose top-performing patterns and per-symbol results.

```mermaid
flowchart TD
H["Signal History Records"] --> G["Group by Signal Type + Timeframe"]
G --> M["Compute Metrics:<br/>Win Rate, ROI, Avg Return,<br/>Sharpe Ratio, Max DD"]
M --> B["Serialize Backtest Groups"]
```

**Diagram sources**
- [backtests.py:45-138](file://src/apps/signals/backtests.py#L45-L138)
- [backtest_support.py:34-69](file://src/apps/signals/backtest_support.py#L34-L69)

**Section sources**
- [backtests.py:26-271](file://src/apps/signals/backtests.py#L26-L271)
- [backtest_support.py:34-69](file://src/apps/signals/backtest_support.py#L34-L69)

## Dependency Analysis
- Strategy depends on StrategyRule and StrategyPerformance relationships; StrategyRule embeds pattern slug and context filters.
- Strategy discovery depends on pattern statistics for success rates and temperature; also uses regime and cycle detection.
- Risk-adjusted decisions depend on latest decision and computed risk metrics; publishes final signals.

```mermaid
classDiagram
class Strategy {
+int id
+string name
+string description
+bool enabled
+created_at
+rules : StrategyRule[]
+performance : StrategyPerformance
}
class StrategyRule {
+int strategy_id
+string pattern_slug
+string regime
+string sector
+string cycle
+float min_confidence
}
class StrategyPerformance {
+int strategy_id
+int sample_size
+float win_rate
+float avg_return
+float sharpe_ratio
+float max_drawdown
+updated_at
}
Strategy "1" o-- "many" StrategyRule : "has"
Strategy "1" o-- "1" StrategyPerformance : "has"
```

**Diagram sources**
- [models.py:168-236](file://src/apps/signals/models.py#L168-L236)

**Section sources**
- [models.py:168-236](file://src/apps/signals/models.py#L168-L236)

## Performance Considerations
- Strategy discovery caps candidate count and requires minimum sample size to avoid overfitting.
- Sharpe ratio threshold ensures positive risk-adjusted returns.
- Rolling windows in pattern statistics prevent stale signals from dominating lifecycle decisions.
- Risk-adjusted decisions avoid unnecessary trades when risk-adjusted score is below thresholds.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
- Strategies not appearing: verify evaluation cycle ran and strategies meet minimum sample size and thresholds.
- Low strategy enablement: check pattern success rates and lifecycle state; confirm sufficient samples and success rate thresholds.
- Risk-adjusted signals unchanged: compare material delta thresholds for score and confidence; ensure new decision differs meaningfully.
- Backtest discrepancies: confirm lookback windows and grouping criteria; ensure result_return/result_drawdown are populated.

**Section sources**
- [strategy.py:270-277](file://src/apps/patterns/domain/strategy.py#L270-L277)
- [success.py:128-277](file://src/apps/patterns/domain/success.py#L128-L277)
- [risk.py:274-291](file://src/apps/patterns/domain/risk.py#L274-L291)
- [backtests.py:45-138](file://src/apps/signals/backtests.py#L45-L138)

## Conclusion
The strategy development system combines automated discovery, regime/cycle-aware adaptation, and robust performance tracking with risk-adjusted decision making. The evaluation cycle continuously refines strategies and patterns, while lifecycle mechanisms ensure only viable strategies remain active. Backtesting and benchmarking provide quantitative validation against market conditions.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Practical Examples and Optimization Techniques
- Constructing a strategy: combine top pattern tokens, constrain by regime and cycle, and set minimum confidence thresholds; review performance metrics and enable/disable accordingly.
- Parameter optimization: adjust minimum sample size, win rate, Sharpe ratio, and drawdown thresholds to balance discovery vs. stability; monitor pattern success lifecycle transitions.
- Benchmarking: compare strategies via Sharpe ratio, win rate, and maximum drawdown; use backtests to validate across symbols and timeframes.

[No sources needed since this section provides general guidance]