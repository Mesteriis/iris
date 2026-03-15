# Lazy Investor AI Plan

## Status

This document is no longer an abstract vision note.

As of 2026-03-14, the rollout described here reached a platform-grade state in code and is backed by normative architecture artifacts.

Its purpose is to record how the AI layer should fit into the **already accepted** IRIS architecture model.

This is a bridge document between the current `hypothesis_engine` and the future shared `core.ai` product capability layer.

Normative rollout artifacts now exist in:

- ADR 0015 and companion architecture policy documents
- AI runtime policy
- AI performance budgets
- delivery and architecture governance docs

Already implemented:

- migration of `hypothesis_generate` to a capability-aware executor
- `brief_generate` as an analytical snapshot surface
- `explain_generate` as a bounded explanation capability
- AI operator and admin surfaces in the existing `control_plane`
- prompt, task, and provider separation with enforced prompt policy

## Goal

Build a unified AI layer for IRIS that:

- goes beyond `hypothesis_engine` only;
- works with multiple real providers;
- is enabled by capability-by-configuration rather than a single boolean feature flag;
- supports `hypothesis_generate`, `notification_humanize`, `brief_generate`, and `explain_generate`;
- respects the language from instance settings or an explicitly passed `language` / `locale`;
- does not break the existing service/runtime governance model;
- does not turn deterministic domains into an LLM-first system.

This must not become “yet another AI app.” It must become a proper platform layer for the product scenario of a calm, low-friction investor workflow.

## Repository Architectural Context

The AI plan must live inside the already accepted operating model of the repository.

Implications:

- AI must fit into `core/`, `apps/`, and `runtime/`, not create a parallel architecture;
- AI governance must use the same policy-doc and ADR model as the rest of the repo;
- heavy AI paths must obey runtime idempotency, retry, and concurrency rules;
- AI surfaces must respect the existing mode/profile-aware HTTP model;
- briefs and AI-derived reads must fit analytical snapshot semantics rather than living on an isolated “AI island.”

## Current Repository State

IRIS already has a working AI contour, but it is not yet platform-grade.

What already exists:

- generation flow for hypotheses;
- deterministic evaluation jobs for hypotheses;
- read surface, job triggers, and SSE insights.

Main architectural debts:

1. `enable_hypothesis_engine` is still the primary switch.
2. Prompt data and infrastructure routing are still too close together.
3. `HYPOTHESIS_OUTPUT_SCHEMA` is not yet a true output-contract enforcement path.
4. Heuristic fallback is still too magical.
5. Generation and evaluation are conceptually different, but still named too generically in the product model.

## Main Architectural Principle

AI is not “new business logic.”

AI is the next layer on top of already existing machine-canonical domains.

That means:

- `signals`, `predictions`, `cross_market`, `portfolio`, `anomalies`, and `market_structure` continue to compute canonical facts themselves;
- AI operates on typed facts, events, and read models;
- AI explains, humanizes, summarizes, and generates hypotheses or briefs;
- AI does not become the source of trading truth.

## Non-Negotiable Rules

### 1. Deterministic Domains Remain Canonical

LLMs do not replace:

- signal generation
- market structure
- portfolio rules
- risk rules
- automation-critical decisions

All automation-critical outputs remain deterministic.

### 2. LLM Adapters Do Not Live in Domain Services

Do not pull `httpx`, provider SDKs, OpenAI, Ollama, or similar clients into:

- domain services
- analytical services
- regular orchestration services

All external AI calls must live in a shared AI platform layer.

### 3. Feature Flags Stop Being the Primary Source of Truth

A capability is available only if:

- at least one real provider is configured;
- that provider is allowed for the capability;
- runtime policy permits execution in the current mode/profile;
- health and degraded-state policy do not block execution.

A single boolean like `enable_hypothesis_engine` must not decide the fate of the entire AI layer.

### 4. Prompts Must Not Control Infrastructure Routing

Prompts and prompt variables may store only:

- task-specific context;
- style and wording hints;
- safe semantic defaults.

Prompts must not store or mutate:

- provider routing;
- base URLs;
- auth or transport config;
- capability enablement.

### 5. Heuristic Fallback Is a Degraded Strategy, Not a Peer Provider

Rule-based fallback is useful, but it must not:

- count as “AI enabled”;
- hide provider outage;
- be treated as a peer to real LLM providers;
- silently mask validation or network failures.

### 6. Structured-First, Humanized-Second

Typed contract comes first in all AI use cases.

The system must first produce a typed result or typed canonical input/output envelope, and only then add humanized text where the capability actually requires it.

### 7. AI Execution Must Respect the Language / Locale Contract

AI capabilities must not guess output language on their own.

Language must come from a formal and predictable source:

- explicit `language` / `locale` for the current request, job trigger, or delivery target;
- stored preference if such a layer exists later;
- instance default from `settings.language`;
- fallback to `en`.

Machine-canonical fields remain language-neutral.

### 8. Context Serialization Is a Separate Execution Concern

Typed context bundles must not leak directly into prompts “as whatever happened to be available.”

Flow:

1. a deterministic context builder assembles typed facts;
2. the execution layer chooses a context transport format;
3. only then is context serialized into prompt input.

## Capability Model

Top-level capabilities must stay compact.

The platform layer should define a small set of stable capabilities, while detail lives in typed input and output contracts rather than in a bloated registry surface.

## Capability, Task, Prompt, Provider: Explicit Separation

The system must distinguish four different concepts.

### Capability

This is the runtime, policy, and exposure unit.

Capability defines:

- whether something may run at all;
- which providers are allowed;
- which execution modes are valid;
- which degraded policy applies;
- which API and runtime surfaces are exposed.

### Task

This is the concrete prompt contract inside a capability.

Tasks are not provider routing and not feature flags.

### Prompt

This is a versioned template, schema, or style artifact for a task.

Prompt is responsible for:

- semantic defaults;
- wording constraints;
- safe style behavior.

### Provider

This is the infrastructure adapter.

It owns transport details, auth, limits, and concrete execution mechanics.

## Language / Locale Contract

Language must be part of the AI execution contract, not prompt magic.

### Resolution Order

1. explicit language for the current response
2. future stored preference target
3. `settings.language` as instance default
4. fallback `en`

### Prompt Interaction

Prompt may use language only as semantic execution input:

- wording selection
- tone/profile selection
- language-aware output-schema constraints

Prompt must not override the effective language decided by the execution contract.

### Execution Metadata

Each AI result should preserve:

- requested language
- effective language
- requested provider
- actual provider
- degraded/offline status

### Output Rule

If a capability returns human-facing text, it must be generated in the effective language.

Forbidden:

- silent provider-default language
- mixed-language output without explicit mode
- losing the reason why a given language was chosen

## Context Transport Contract

### General Principle

Inside domain layers, the source of truth remains the typed context bundle.

At the boundary between domain code and AI execution, that context is transformed into one of the supported transport formats:

- `json`
- `compact_json`
- `toon`
- `csv`

The execution layer chooses this by policy, not the domain service and not the prompt.

### Practical Selection Rule

- `json` — maximum compatibility and simplest pipeline
- `compact_json` — still JSON, but with reduced noise
- `toon` — repeated row-like objects, logs, candles, tables, metrics
- `csv` — flat table-like data where nesting is unnecessary

### Formal Rules

- one task may allow only a bounded whitelist of formats
- prompt does not serialize context itself
- the execution layer provides already serialized input plus metadata about the format

### Why This Matters

Without this policy, the system degrades into a mixture of arbitrary payload shapes and incompatible prompt assumptions.

### Prompt / Task Interaction

A task may constrain allowed context formats, but the execution layer still chooses the final effective format.

### Execution Metadata

Each AI execution result should link back to:

- context format
- prompt version
- provider
- language
- capability
- task

## Provider Model

Replace scattered provider settings with a typed provider registry.

Each provider entry should include:

- provider key
- transport config
- health state
- latency and cost metadata
- compliance tier
- allowed capabilities
- optional capability-specific overrides

### Requested vs Actual Provider

Each execution result must distinguish between:

- requested provider
- actual provider

This is required for fallback, observability, and auditability.

## Output Contract Enforcement

“Ask the prompt to return JSON” is not enough.

The platform needs a real schema-first execution path with:

- validation
- typed result parsing
- explicit failure classes
- degraded status handling

Minimum statuses:

- healthy
- degraded
- offline
- invalid_output
- unavailable

LLM output must not silently become “something close enough.”

## Shared AI Platform Layer

The first safe step is not a new giant app, but a shared `core.ai` layer.

Target structure:

```text
backend/src/core/ai/
  capabilities/
  contracts/
  execution/
  prompts/
  providers/
  registry/
  validation/
  degraded/
```

Role:

- registry for capabilities and providers
- execution engine
- prompt policy
- output validation
- degraded-mode handling
- common AI contracts

### What Moves First

Initial refactor should stay narrow:

- `ReasoningService` becomes thin orchestration over `AIExecutor.execute(...)`

That yields a platform layer without an immediate large rename of domain apps.

## What to Do With the Current `hypothesis_engine`

Do not start with a big rename under `lazy_investor`.

The correct path:

### Phase 1

Keep `src/apps/hypothesis_engine` as a domain app but move it onto shared `core.ai`.

### Phase 2

Add `notification_humanize` on top of the shared platform.

### Phase 3

Add `brief_generate` as an analytical snapshot surface.

### Phase 4

Only after at least two new real capabilities stabilize, decide whether a separate `src/apps/lazy_investor` is justified.

Rule:

**Do not create a large `apps/lazy_investor` package just for naming aesthetics.**

## Generation vs Evaluation: Explicit Separation

This must become an architectural invariant.

### `hypothesis_generate`

This is an AI capability:

- depends on provider availability
- uses prompt, task, and provider routing
- publishes AI-derived artifacts

### `hypothesis_evaluation`

This is deterministic service lifecycle:

- uses ordinary jobs, locks, and tracked operations
- does not depend on real LLM-provider availability
- is not disabled together with generation surfaces
- remains observable even when AI generation is offline

Read surfaces for hypotheses and evaluations must not disappear only because a provider is absent.

## Runtime Gating: Not Only Settings

Migration to capability-by-configuration must affect three layers:

1. HTTP surface mounting
2. worker-group existence
3. automatically enabled background jobs

AI availability must not be decided in one place and bypassed in two others.

## Mode / Profile Matrix

The AI surface must be mode-aware.

Minimum principle:

- human-facing reads may exist without generation;
- generation, admin, and streaming surfaces do not need to be available in the HA embedded profile;
- public availability follows the same governance model as the rest of the HTTP surface.

## Failure Domains and Degraded Modes

### `healthy`

- at least one real provider exists
- validation path works
- capability runs in normal mode

### `degraded`

- a fallback chain is used
- or the capability is temporarily allowed only via deterministic degraded strategy

Examples:

- `notification_humanize` may degrade to template-based humanization
- `explain_generate` may degrade to a bounded deterministic summary
- `hypothesis_generate` should not silently degrade into pseudo-LLM behavior unless product policy explicitly allows it

### `offline`

- no real providers are available
- generation capabilities do not run
- read surfaces remain
- deterministic evaluation continues
- runtime returns typed `unavailable` or `skipped` instead of pretending success

## Do Not Block the Rest of Runtime

This is a separate invariant.

Heavy AI capabilities must never run on shared analytical worker lanes.

Rules:

- dedicated AI worker groups
- dedicated concurrency budgets
- dedicated timeout and performance budgets
- no AI outage impact on deterministic signal, prediction, or portfolio paths

## Storage and Observability

Do not force everything into a universal `AIArtifact` table.

`hypotheses`, `notifications`, and `briefs` have different lifecycles.

Instead:

- keep artifact-specific storage;
- standardize a shared execution-metadata envelope.

Minimum metadata:

- capability
- task
- prompt version
- provider
- language
- degraded state
- validation status
- request / operation linkage
- timestamps

For hypotheses, this is an extension of already-strong traceability rather than a redesign.

Minimum metrics:

- provider latency
- provider failure rate
- validation failure rate
- degraded/offline rate by capability
- worker saturation
- output-size and timeout pressure where relevant

## Notification Humanization as the First New Capability

The first new capability after migration should be `notification_humanize`, not `brief_generate`.

Why:

- short context
- bounded output
- easier degraded strategy
- clearer product value

## Briefs as an Analytical Snapshot Surface

`brief_generate` should behave as an analytical snapshot surface:

- async generation
- cached read surface
- bounded payload
- explicit freshness metadata

It must not become a hidden synchronous endpoint that does heavyweight provider work during reads.

## Operator / Admin Surface

Operator and admin control for AI should live in existing governance surfaces rather than in a disconnected AI mini-admin.

Expose:

- provider health
- capability availability
- prompt policy state
- degraded or offline reason
- selected execution metrics

## Prompt Policy

Prompt policy must explicitly constrain:

- allowed variables
- max context size
- allowed context formats
- provider restrictions
- language behavior
- output schema
- safety and non-routing guarantees

## Rollout Plan

### Stage 1. Governance and Foundations

- ADR and policy alignment
- capability model
- prompt policy
- failure-domain rules

### Stage 2. `core.ai` Foundation

- registry
- executor
- provider adapters
- validation

### Stage 3. Hypothesis Migration

- move `hypothesis_generate` to the shared executor
- keep deterministic evaluation separate

### Stage 4. Notification Humanization

- add first new real capability
- validate degraded mode and bounded contracts

### Stage 5. Briefs

- add asynchronous brief generation
- expose read surface with snapshot semantics

### Stage 6. Optional Product-Layer Expansion

- only if multiple capabilities justify a broader AI product layer

## What We Intentionally Do Not Do Right Now

- turn the platform into an LLM-first architecture
- replace deterministic truth with provider output
- introduce a giant “lazy investor” app for naming alone
- let prompts control transport or provider routing
- let AI ride on shared critical worker lanes

## Definition of Done

The AI layer is considered integrated correctly when:

- shared `core.ai` exists as the execution foundation;
- deterministic domains remain canonical;
- capability availability is not controlled by one boolean flag;
- prompt, task, capability, and provider are separated;
- language is resolved formally and predictably;
- output validation is explicit;
- degraded and offline states are observable and typed;
- generation and evaluation are explicitly separated;
- AI workloads cannot destabilize deterministic runtime paths.

## Main Conclusion

The correct path for IRIS is not “add another AI app.”

The correct path is:

1. formalize shared AI execution foundations;
2. keep deterministic truth in domain layers;
3. expose compact product capabilities on top of that foundation;
4. grow AI surfaces only where they add bounded, explainable value.
