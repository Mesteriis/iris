# Continuation Patterns

<cite>
**Referenced Files in This Document**
- [__init__.py](file://src/apps/patterns/domain/detectors/continuation/__init__.py)
- [base.py](file://src/apps/patterns/domain/base.py)
- [utils.py](file://src/apps/patterns/domain/utils.py)
- [engine.py](file://src/apps/patterns/domain/engine.py)
- [registry.py](file://src/apps/patterns/domain/registry.py)
- [context.py](file://src/apps/patterns/domain/context.py)
- [success.py](file://src/apps/patterns/domain/success.py)
- [evaluation.py](file://src/apps/patterns/domain/evaluation.py)
- [test_continuation_detectors_real.py](file://tests/apps/patterns/test_continuation_detectors_real.py)
- [test_continuation_guard_branches.py](file://tests/apps/patterns/test_continuation_guard_branches.py)
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
This document explains the continuation pattern detectors implemented in the system. It covers detection algorithms for flag, pennant, cup-and-handle, and several other continuation setups; the formation criteria and validation steps; breakout confirmation techniques; thresholds and volume confirmation; time-frame considerations; detector configuration parameters; false-positive prevention mechanisms; and integration with the broader pattern evaluation system.

## Project Structure
The continuation pattern detectors live under the patterns domain and are built into the global detector registry. They rely on shared utilities for price/volume analysis and integrate with the pattern engine, success validation, and context enrichment systems.

```mermaid
graph TB
subgraph "Patterns Domain"
D["Detectors<br/>continuation/__init__.py"]
U["Utilities<br/>utils.py"]
E["Engine<br/>engine.py"]
R["Registry<br/>registry.py"]
C["Context<br/>context.py"]
S["Success Validation<br/>success.py"]
B["Base Types<br/>base.py"]
end
subgraph "Tests"
T1["Real Shape Tests<br/>test_continuation_detectors_real.py"]
T2["Guard Branch Tests<br/>test_continuation_guard_branches.py"]
end
D --> U
E --> D
E --> R
E --> S
E --> C
E --> B
T1 --> D
T2 --> D
```

**Diagram sources**
- [__init__.py:1-374](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L1-L374)
- [utils.py:1-157](file://src/apps/patterns/domain/utils.py#L1-L157)
- [engine.py:1-212](file://src/apps/patterns/domain/engine.py#L1-L212)
- [registry.py:1-102](file://src/apps/patterns/domain/registry.py#L1-L102)
- [context.py:1-214](file://src/apps/patterns/domain/context.py#L1-L214)
- [success.py:1-277](file://src/apps/patterns/domain/success.py#L1-L277)
- [base.py:1-35](file://src/apps/patterns/domain/base.py#L1-L35)
- [test_continuation_detectors_real.py:1-186](file://tests/apps/patterns/test_continuation_detectors_real.py#L1-L186)
- [test_continuation_guard_branches.py:1-117](file://tests/apps/patterns/test_continuation_guard_branches.py#L1-L117)

**Section sources**
- [__init__.py:1-374](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L1-L374)
- [engine.py:1-212](file://src/apps/patterns/domain/engine.py#L1-L212)
- [registry.py:1-102](file://src/apps/patterns/domain/registry.py#L1-L102)

## Core Components
- PatternDetector base class defines the interface and shared metadata (category, supported timeframes, enabled flag).
- Continuation detectors implement detect() returning PatternDetection entries when conditions are met.
- Utilities provide helpers for price/volume/window analysis and indicator mapping.
- Engine orchestrates detector selection, execution, success validation, and persistence.
- Registry controls which detectors are active per timeframe.
- Success validation adjusts confidence based on historical pattern performance.
- Context enrichment augments signals with regime, volatility, liquidity, and cycle alignment.

Key detector categories covered:
- Flag (bull/bear)
- Pennant
- Cup and Handle
- Breakout Retest
- Consolidation Breakout
- High Tight Flag
- Channel Breakout/Breakdown (rising/falling)
- Measured Move (bull/bear)
- Base Breakout
- Volatility Contraction Breakout/Down (bull/bear)
- Pullback Continuation (bull/bear)
- Squeeze Breakout
- Trend Pause Breakout
- Handle Breakout
- Stair Step Continuation

**Section sources**
- [base.py:21-35](file://src/apps/patterns/domain/base.py#L21-L35)
- [__init__.py:10-374](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L10-L374)
- [utils.py:18-157](file://src/apps/patterns/domain/utils.py#L18-L157)
- [engine.py:29-72](file://src/apps/patterns/domain/engine.py#L29-L72)
- [registry.py:94-102](file://src/apps/patterns/domain/registry.py#L94-L102)
- [success.py:191-277](file://src/apps/patterns/domain/success.py#L191-L277)
- [context.py:127-187](file://src/apps/patterns/domain/context.py#L127-L187)

## Architecture Overview
The continuation detection pipeline:
- Engine loads active detectors for the given timeframe.
- Detectors compute confidence using price/volume windows and thresholds.
- Success validation scales confidence based on historical success rates.
- Context enrichment applies regime, volatility, liquidity, and cycle adjustments.
- Results are persisted as Signals.

```mermaid
sequenceDiagram
participant Eng as "PatternEngine"
participant Reg as "Registry"
participant Det as "Continuation Detector"
participant Suc as "Success Validation"
participant Con as "Context Enrichment"
participant DB as "Persistence"
Eng->>Reg : Load active detectors (timeframe)
Reg-->>Eng : Detector list
loop For each detector
Eng->>Det : detect(candles, indicators)
Det-->>Eng : PatternDetection[]
Eng->>Suc : apply_pattern_success_validation(...)
Suc-->>Eng : Adjusted PatternDetection or None
Eng->>Con : apply_pattern_context(...)
Con-->>Eng : Final PatternDetection
Eng->>DB : Insert/Update Signal
end
```

**Diagram sources**
- [engine.py:29-72](file://src/apps/patterns/domain/engine.py#L29-L72)
- [registry.py:94-102](file://src/apps/patterns/domain/registry.py#L94-L102)
- [success.py:191-277](file://src/apps/patterns/domain/success.py#L191-L277)
- [context.py:127-187](file://src/apps/patterns/domain/context.py#L127-L187)

## Detailed Component Analysis

### Flag Pattern Detection
Formation criteria:
- Requires minimum length window and computes pole move and pullback magnitude.
- Bull flag: pole move positive above threshold, pullback negative and bounded, channel slope decreasing; last close below recent highs.
- Bear flag: inverse conditions.
- Confidence increases with pole strength and volume confirmation.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 30"]
Len --> |Fail| EndEmpty["Return []"]
Len --> |Pass| Win["Take [-35:] window"]
Win --> Prices["Compute closes"]
Prices --> Pole["Compute pole = pct_change(last12, -25)"]
Prices --> Pull["Compute pullback = pct_change(last, last12)"]
Prices --> Slope["Compute channel_slope = linear_slope(lasts10)"]
subgraph "Bull Case"
PBull["pole > 0.05<br/>pullback < 0<br/>abs(pullback) < abs(pole)*0.5<br/>slope < 0"]
PBull --> LHB["prices[-1] >= max(prices[-5:]) ?"]
LHB --> |Yes| EndEmpty
LHB --> |No| ConfB["confidence = 0.68 + pole + volume_ratio*0.05"]
end
subgraph "Bear Case"
PBea["pole < -0.05<br/>pullback > 0<br/>abs(pullback) < abs(pole)*0.5<br/>slope > 0"]
PBea --> LHT["prices[-1] <= min(prices[-5:]) ?"]
LHT --> |Yes| EndEmpty
LHT --> |No| ConfB2["confidence = 0.68 + abs(pole) + volume_ratio*0.05"]
end
ConfB --> Emit["Emit detection"]
ConfB2 --> Emit
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:30-51](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L30-L51)

**Section sources**
- [__init__.py:30-51](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L30-L51)
- [utils.py:18-115](file://src/apps/patterns/domain/utils.py#L18-L115)
- [test_continuation_guard_branches.py:11-28](file://tests/apps/patterns/test_continuation_guard_branches.py#L11-L28)

### Pennant Pattern Detection
Formation criteria:
- Minimum length and recent consolidation range threshold.
- Trend pole move threshold and converging channel (high slope negative, low slope positive).
- Breakout threshold on recent bars.
- Confidence increases with pole move and volume confirmation.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 28"]
Len --> |Fail| EndEmpty["Return []"]
Len --> |Pass| Win["Take [-30:] window"]
Win --> Prices["Compute closes"]
Prices --> Pole["pole_move = abs(pct_change(-12, -25))"]
Prices --> Range["consolidation_range = window_range(lasts10)/max"]
Prices --> HSlope["high_slope = linear_slope(highs[-10:])"]
Prices --> LSlope["low_slope = linear_slope(lows[-10:])"]
Prices --> Brk["breakout = abs(pct_change(last, -4)) > 0.02"]
Cond["pole_move>=0.05<br/>range<=0.05<br/>HSlope<0<LSlope<br/>breakout"] --> |Fail| EndEmpty
Cond --> Conf["confidence = 0.67 + pole_move + max(volume_ratio-1,0)*0.04"]
Conf --> Emit["Emit detection"]
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:57-71](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L57-L71)

**Section sources**
- [__init__.py:57-71](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L57-L71)
- [utils.py:100-115](file://src/apps/patterns/domain/utils.py#L100-L115)
- [test_continuation_guard_branches.py:30-31](file://tests/apps/patterns/test_continuation_guard_branches.py#L30-L31)

### Cup and Handle Pattern Detection
Formation criteria:
- Left/right rims above trough threshold; symmetry constraint.
- Handle low within depth limits.
- Breakout above right rim.
- Confidence increases with cup depth.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 60"]
Len --> |Fail| EndEmpty["Return []"]
Len --> |Pass| Win["Take [-80:] window"]
Win --> Prices["Compute closes"]
Prices --> Rim["left_rim=max[:20]<br/>right_rim=max[-20:]"]
Prices --> Trgh["trough=min[20:-20]"]
Prices --> Sym["abs(left_rim-right_rim)/max <= 0.04"]
Prices --> Depth["cup_depth = left_rim - trough"]
Prices --> HandleLow["handle_low = min(last12)"]
Prices --> DepthLim["left_rim - handle_low <= depth * 0.4"]
Prices --> Break["prices[-1] > right_rim"]
Cond["Rims > trough*1.08<br/>Symmetry OK<br/>Depth limit OK<br/>Breakout OK"] --> |Fail| EndEmpty
Cond --> Conf["confidence = 0.7 + depth/left_rim"]
Conf --> Emit["Emit detection"]
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:77-97](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L77-L97)

**Section sources**
- [__init__.py:77-97](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L77-L97)
- [test_continuation_guard_branches.py:33-48](file://tests/apps/patterns/test_continuation_guard_branches.py#L33-L48)

### Breakout Retest Detection
Validation:
- Defines recent retest boundary near support/resistance.
- Confirms breakout bar beyond retest level.
- Confidence increases with recent volume expansion.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 30"]
Len --> |Fail| EndEmpty["Return []"]
Len --> Prices["Compute prices[-40:]"]
Prices --> Res["resistance = max[-25:-6]"]
Prices --> Sup["support = min[-25:-6]"]
Prices --> Brk["breakout_bar = max[-6:-3]"]
Prices --> Ret["retest_low = min[-3:]"]
Prices --> Last["last = prices[-1]"]
Cond["Bull: breakout_bar>Res AND retest_low>=Res*0.985 AND last>=Res<br/>OR Bear: breakout_bar<Sup AND retest_low<=Sup*1.015 AND last<=Sup"] --> |Fail| EndEmpty
Cond --> Conf["confidence = 0.66 + max(volume_ratio[-20:]-1,0)*0.05"]
Conf --> Emit["Emit detection"]
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:103-118](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L103-L118)

**Section sources**
- [__init__.py:103-118](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L103-L118)
- [utils.py:106-115](file://src/apps/patterns/domain/utils.py#L106-L115)

### Consolidation Breakout Detection
Criteria:
- Tight consolidation range threshold.
- Final bar breaks out of the range.
- Confidence increases with volume expansion and recent price change.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 24"]
Len --> |Fail| EndEmpty["Return []"]
Len --> Win["Window = [-24:]"]
Win --> Prices["Compute closes"]
Prices --> Range["tight_range = range/prices[-2]"]
Prices --> HL["range_high/max<br/>range_low/min"]
Prices --> Last["last = prices[-1]"]
Cond["tight_range <= 0.06<br/>last outside [range_low, range_high]"] --> |Fail| EndEmpty
Cond --> Conf["confidence = 0.65 + max(volume_ratio-1,0)*0.08 + abs(change)*0.6"]
Conf --> Emit["Emit detection"]
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:124-139](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L124-L139)

**Section sources**
- [__init__.py:124-139](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L124-L139)
- [utils.py:100-115](file://src/apps/patterns/domain/utils.py#L100-L115)

### High Tight Flag Detection
Criteria:
- Minimum pole move and tight consolidation threshold.
- Breakout above recent high.
- Confidence increases with pole move and volume.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 30"]
Len --> |Fail| EndEmpty["Return []"]
Len --> Win["Window = [-32:]"]
Win --> Prices["Compute closes"]
Prices --> Pole["pole = pct_change(-12, -28)"]
Prices --> Con["contraction = (hh-ll)/hh"]
Prices --> HH["prices[-1] > consolidation_high"]
Cond["pole >= 0.1<br/>contraction <= 0.06<br/>breakout OK"] --> |Fail| EndEmpty
Cond --> Conf["confidence = 0.72 + pole*0.6 + max(volume_ratio-1,0)*0.04"]
Conf --> Emit["Emit detection"]
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:145-158](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L145-L158)

**Section sources**
- [__init__.py:145-158](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L145-L158)

### Channel Continuation Detection
Bull case: both highs/lows slopes negative and price above recent high.
Bear case: both slopes positive and price below recent low.
Confidence proportional to slope magnitudes.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 35"]
Len --> |Fail| EndEmpty["Return []"]
Len --> Win["Window = [-45:]"]
Win --> PH["price_highs[-16:]"]
Win --> PL["price_lows[-16:]"]
PH --> HS["high_slope = linear_slope(...)"]
PL --> LS["low_slope = linear_slope(...)"]
Win --> Latest["latest = close[-1]"]
subgraph "Bull"
BC["HS < 0<br/>LS < 0<br/>latest > max(highs[-10:-1])"]
BC --> CB["confidence = 0.66 + abs(HS)/latest * 6"]
end
subgraph "Bear"
SC["HS > 0<br/>LS > 0<br/>latest < min(lows[-10:-1])"]
SC --> CS["confidence = 0.66 + abs(LS)/latest * 6"]
end
CB --> Emit["Emit detection"]
CS --> Emit
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:166-184](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L166-L184)

**Section sources**
- [__init__.py:166-184](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L166-L184)

### Measured Move Detection
Criteria:
- Leg-one, retracement, leg-two moves with directional thresholds.
- Confidence increases with similarity of leg lengths and volume.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 36"]
Len --> |Fail| EndEmpty["Return []"]
Len --> Prices["prices[-40:]"]
Prices --> L1["leg_one = pct_change(-24, -36)"]
Prices --> Ret["retrace = pct_change(-12, -24)"]
Prices --> L2["leg_two = pct_change(-1, -12)"]
subgraph "Bull"
B1["leg_one > 0.04<br/>retrace < 0<br/>abs(retrace) < abs(leg_one)*0.7<br/>leg_two > 0.03"]
B1 --> CB["confidence = 0.67 + min_diff + max(volume_ratio-1,0)*0.03"]
end
subgraph "Bear"
S1["leg_one < -0.04<br/>retrace > 0<br/>abs(retrace) < abs(leg_one)*0.7<br/>leg_two < -0.03"]
S1 --> CS["confidence = 0.67 + min_diff + max(volume_ratio-1,0)*0.03"]
end
CB --> Emit["Emit detection"]
CS --> Emit
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:192-208](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L192-L208)

**Section sources**
- [__init__.py:192-208](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L192-L208)

### Base Breakout Detection
Criteria:
- Early advance threshold over recent segment.
- Base range narrow and breakout above recent high.
- Confidence increases with advance and volume.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 30"]
Len --> |Fail| EndEmpty["Return []"]
Len --> Win["Window = [-34:]"]
Win --> Prices["Compute closes"]
Prices --> Adv["advance = pct_change(-15, 0)"]
Prices --> BaseHL["base_high = max(-15:-1]<br/>base_low = min(-15:-1)"]
Cond["advance >= 0.05<br/>range/base_high <= 0.05<br/>prices[-1] > base_high"] --> |Fail| EndEmpty
Cond --> Conf["confidence = 0.68 + advance + max(volume_ratio-1,0)*0.05"]
Conf --> Emit["Emit detection"]
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:214-228](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L214-L228)

**Section sources**
- [__init__.py:214-228](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L214-L228)

### Volatility Contraction Breakout/Down Detection
Criteria:
- Early vs late range comparison with contraction threshold.
- Breakout above recent high (bull) or below recent low (bear).
- Confidence increases with contraction magnitude.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 32"]
Len --> |Fail| EndEmpty["Return []"]
Len --> Prices["prices[-36:]"]
Prices --> ER["early_range = range(-24:-12)/price"]
Prices --> LR["late_range = range(-12:-1)/price"]
subgraph "Bull"
B1["LR < ER*0.75<br/>prices[-1] > recent_high"]
B1 --> CB["confidence = 0.67 + max(ER-LR,0)"]
end
subgraph "Bear"
S1["LR < ER*0.75<br/>prices[-1] < recent_low"]
S1 --> CS["confidence = 0.67 + max(ER-LR,0)"]
end
CB --> Emit["Emit detection"]
CS --> Emit
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:236-255](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L236-L255)

**Section sources**
- [__init__.py:236-255](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L236-L255)

### Pullback Continuation Detection
Criteria:
- Trend leg, retracement, and resumption moves with directional thresholds.
- Confidence increases with leg and resumption strengths.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 28"]
Len --> |Fail| EndEmpty["Return []"]
Len --> Prices["prices[-30:]"]
Prices --> TL["trend_leg = pct_change(-10, -24)"]
Prices --> Ret["retrace = pct_change(-4, -10)"]
Prices --> Res["resumption = pct_change(-1, -4)"]
subgraph "Bull"
B1["TL > 0.04<br/>Ret < 0<br/>abs(Ret) < abs(TL)*0.5<br/>Res > 0.015"]
B1 --> CB["confidence = 0.66 + TL + Res"]
end
subgraph "Bear"
S1["TL < -0.04<br/>Ret > 0<br/>abs(Ret) < abs(TL)*0.5<br/>Res < -0.015"]
S1 --> CS["confidence = 0.66 + abs(TL) + abs(Res)"]
end
CB --> Emit["Emit detection"]
CS --> Emit
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:263-279](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L263-L279)

**Section sources**
- [__init__.py:263-279](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L263-L279)

### Squeeze Breakout Detection
Criteria:
- Pre-breakout range threshold.
- Breakout above recent high.
- Confidence increases with volume.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 25"]
Len --> |Fail| EndEmpty["Return []"]
Len --> Win["Window = [-25:]"]
Win --> Prices["Compute closes"]
Prices --> PR["pre_range = range(-12:-1)/max"]
Prices --> Break["prices[-1] > max"]
Cond["pre_range <= 0.04<br/>breakout"] --> |Fail| EndEmpty
Cond --> Conf["confidence = 0.67 + max(volume_ratio-1,0)*0.08"]
Conf --> Emit["Emit detection"]
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:285-297](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L285-L297)

**Section sources**
- [__init__.py:285-297](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L285-L297)

### Trend Pause Breakout Detection
Criteria:
- Early advance threshold and small pause range.
- Breakout above recent high.
- Confidence increases with advance.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 26"]
Len --> |Fail| EndEmpty["Return []"]
Len --> Prices["prices[-28:]"]
Prices --> Adv["advance = pct_change(-8, 0)"]
Prices --> Pause["pause_range = range(-8:-1)/max"]
Prices --> Break["prices[-1] > max"]
Cond["advance >= 0.05<br/>pause_range <= 0.04<br/>breakout"] --> |Fail| EndEmpty
Cond --> Conf["confidence = 0.66 + advance"]
Conf --> Emit["Emit detection"]
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:303-313](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L303-L313)

**Section sources**
- [__init__.py:303-313](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L303-L313)

### Handle Breakout Detection
Criteria:
- Cup high and handle low relationship.
- Breakout above cup high.
- Confidence increases with volume.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 45"]
Len --> |Fail| EndEmpty["Return []"]
Len --> Win["Window = [-50:]"]
Win --> Prices["Compute closes"]
Prices --> Cup["cup_high = max[:-10]"]
Prices --> HandleLow["handle_low = min[-10:-1]"]
Prices --> Break["prices[-1] > cup_high"]
Cond["handle_low >= cup_high*0.92<br/>breakout"] --> |Fail| EndEmpty
Cond --> Conf["confidence = 0.68 + max(volume_ratio-1,0)*0.05"]
Conf --> Emit["Emit detection"]
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:319-332](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L319-L332)

**Section sources**
- [__init__.py:319-332](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L319-L332)

### Stair Step Continuation Detection
Criteria:
- Stepped higher highs/lower lows with pullback support.
- Final close above recent high.
- Confidence increases with volume.

```mermaid
flowchart TD
Start(["Start detect"]) --> Len["Check length >= 30"]
Len --> |Fail| EndEmpty["Return []"]
Len --> Prices["prices[-30:]"]
Prices --> Steps["step_one: increasing highs"]
Prices --> Hold["pullbacks_hold: min in pullbacks > prior peak"]
Prices --> Break["prices[-1] > max(last8)"]
Cond["steps OK<br/>hold OK<br/>breakout OK"] --> |Fail| EndEmpty
Cond --> Conf["confidence = 0.67 + max(volume_ratio[-20:]-1,0)*0.05"]
Conf --> Emit["Emit detection"]
Emit --> End(["Done"])
```

**Diagram sources**
- [__init__.py:338-348](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L338-L348)

**Section sources**
- [__init__.py:338-348](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L338-L348)

## Dependency Analysis
- Detectors depend on shared utilities for price/volume analysis and windowing.
- Engine composes detectors, success validation, and context enrichment.
- Registry filters detectors by lifecycle and enabled state, and by supported timeframes.
- Success validation reads historical statistics and adjusts confidence.
- Context enrichment pulls regime, sector, and cycle signals to compute alignment factors.

```mermaid
graph LR
Utils["utils.py"] --> Det["continuation/__init__.py"]
Base["base.py"] --> Det
Reg["registry.py"] --> Eng["engine.py"]
Suc["success.py"] --> Eng
Con["context.py"] --> Eng
Det --> Eng
```

**Diagram sources**
- [__init__.py:1-374](file://src/apps/patterns/domain/detectors/continuation/__init__.py#L1-L374)
- [utils.py:1-157](file://src/apps/patterns/domain/utils.py#L1-L157)
- [base.py:1-35](file://src/apps/patterns/domain/base.py#L1-L35)
- [registry.py:94-102](file://src/apps/patterns/domain/registry.py#L94-L102)
- [success.py:191-277](file://src/apps/patterns/domain/success.py#L191-L277)
- [context.py:127-187](file://src/apps/patterns/domain/context.py#L127-L187)
- [engine.py:29-72](file://src/apps/patterns/domain/engine.py#L29-L72)

**Section sources**
- [engine.py:29-72](file://src/apps/patterns/domain/engine.py#L29-L72)
- [registry.py:94-102](file://src/apps/patterns/domain/registry.py#L94-L102)
- [success.py:191-277](file://src/apps/patterns/domain/success.py#L191-L277)
- [context.py:127-187](file://src/apps/patterns/domain/context.py#L127-L187)

## Performance Considerations
- CPU cost estimates are embedded in the catalog; continuation detectors are generally rated moderate to low CPU cost.
- Window sizes vary by detector but are kept reasonable to balance accuracy and speed.
- Volume ratio computation uses a fixed lookback window; tune lookback length via utility if needed.
- Success validation and context enrichment add minimal overhead and are cached per timeframe.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and mitigations:
- Insufficient candles: Many detectors require a minimum number of bars; ensure sufficient history before detection.
- Guard branches failing: Detectors explicitly reject non-conforming shapes; adjust expectations or timeframes.
- No breakout confirmation: Some detectors require breakout beyond retest levels or consolidation boundaries.
- Volume confirmation: Several detectors incorporate volume_ratio; ensure volume data is present and representative.
- Timeframe mismatch: Detectors declare supported timeframes; verify engine uses compatible intervals.
- Success suppression: If historical success rates fall below thresholds, detections may be suppressed or down-weighted.

Evidence from tests:
- Short inputs return empty detections.
- Guard branch tests demonstrate explicit rejections for invalid configurations.
- Real shape tests confirm positive detection for constructed patterns.

**Section sources**
- [test_continuation_detectors_real.py:26-29](file://tests/apps/patterns/test_continuation_detectors_real.py#L26-L29)
- [test_continuation_guard_branches.py:11-117](file://tests/apps/patterns/test_continuation_guard_branches.py#L11-L117)

## Conclusion
The continuation pattern detectors implement robust, threshold-based recognition routines grounded in price dynamics and volume confirmation. They integrate cleanly with the broader pattern evaluation system through the engine, success validation, and context enrichment layers. Configuration is primarily via detector parameters and supported timeframes, while false positives are minimized through guard branches and strict breakout criteria. Historical success rates further refine confidence to improve signal quality.