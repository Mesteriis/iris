IRIS Architecture Guardrails
Controlling Analytical System Complexity

This document defines architectural rules that protect IRIS from uncontrolled system complexity while preserving analytical power.

IRIS intentionally contains multiple analytical layers:

market data ingestion

indicator computation

pattern detection

pattern clusters and hierarchies

regime analysis

cross-market intelligence

signal fusion

investment decisions

liquidity and risk evaluation

portfolio engine

strategy discovery

Without explicit guardrails, systems with this many layers tend to drift into self-inflicted complexity, where architecture becomes harder to operate than the domain logic itself.

The following principles define how IRIS must evolve.

1. Decision Explainability Is a First-Class System Feature

Every generated decision must be explainable.

The system must not behave like a black box composed of many scoring layers.

Each decision must expose a structured decision trace describing:

which signals were considered

which signals were filtered

which factors boosted or degraded confidence

which analytical layer had the decisive impact

what changed relative to the previous decision

Decision trace must include:

input signals

pattern context adjustments

success engine modifications

cross-market influence

regime alignment

risk adjustments

final fusion weights

Explainability must be available through:

API

logs

observability tools

If a decision cannot be explained programmatically, it is considered an architectural defect.

2. Complexity Budget Rule

Every new analytical or runtime subsystem must justify its existence.

Before introducing a new layer, the following questions must be answered:

Does this improve signal quality?

Does this reduce operational risk?

Does this improve explainability?

Does this improve system observability?

If the answer to all of these questions is negative, the feature should not enter the runtime path.

Architectural elegance alone is not a valid justification.

IRIS prioritizes decision quality and system clarity over architectural beauty.

3. Strict Separation Between Research and Production Runtime

Analytical systems naturally accumulate experimental ideas.

IRIS enforces separation between:

Research complexity
Production runtime complexity

Experimental analytics must first exist in research environments where they can be evaluated offline.

Examples:

new pattern detectors

experimental scoring algorithms

new signal families

strategy discovery heuristics

Only after demonstrating measurable value should a feature move into the production runtime pipeline.

Production runtime must remain stable, predictable, and explainable.

4. Deterministic Replay Must Always Be Possible

Every decision in IRIS must be reproducible.

Given:

the same candle history

the same indicator state

the same topology version

the same pattern statistics

the same configuration

the system must produce the same decision outcome.

Replay capability must exist for:

debugging

auditing

backtesting

incident investigation

Replay must allow reconstruction of the full decision pipeline:

candles → indicators → patterns → context → fusion → decision → risk → portfolio action

If a decision cannot be deterministically replayed, the architecture is considered incomplete.

5. Product Value Takes Priority Over Architectural Sophistication

IRIS must never evolve into a system that exists primarily to sustain its own architecture.

Every architectural change must ultimately serve one of the following goals:

better signals
better decision reliability
better explainability
better operational stability
better user-facing insights

If an architectural improvement increases operational complexity without improving these outcomes, it should be reconsidered.

The system must remain focused on delivering clear, reliable market intelligence, not architectural complexity.

6. Control Plane Must Not Outgrow the Product

The event control plane exists to manage routing, compatibility, and runtime topology.

However, the control plane must remain a supporting system, not a primary source of complexity.

Control plane features must be introduced cautiously.

Features such as:

topology drafts

route versioning

compatibility validation

shadow routing

throttling

must only be expanded when they provide real operational benefits.

The control plane must remain understandable to developers who are primarily focused on analytical logic.

7. Signal Fusion Must Remain Calibratable

Signal fusion combines:

pattern signals
regime context
cross-market influence
historical success metrics
risk adjustments

This layer must remain interpretable and tunable.

Fusion models must avoid uncontrolled growth in weighting parameters.

Every fusion factor must satisfy at least one of the following:

clear theoretical justification
measurable predictive power
improved decision stability

If a factor cannot be justified, it should be removed.

8. Risk and Portfolio Layers Require Deterministic Behavior

Once the system crosses from analysis to action, correctness requirements increase dramatically.

Portfolio decisions must be:

deterministic
traceable
auditable

The system must clearly expose:

why a position was opened
why a position was closed
why a position size changed
which constraints affected the decision

Portfolio logic must remain simpler than analytical logic.

9. Observability Is Mandatory

IRIS must maintain deep observability across:

event pipelines
decision generation
signal fusion
portfolio actions
cross-market influence

Observability must allow answering questions such as:

Which layer generated a signal?

Which event triggered a decision?

Which subsystem modified the decision confidence?

Which event route delivered the signal?

Without this visibility, complex event-driven systems become operationally fragile.

Final Principle

IRIS is intentionally designed as a powerful analytical platform.

However, the system must never lose the following property:

A new engineer must be able to understand how a decision is produced.

If system complexity prevents that, the architecture must be simplified.

Powerful systems remain valuable only as long as they remain understandable.