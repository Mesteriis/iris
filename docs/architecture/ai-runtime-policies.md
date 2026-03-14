# AI Runtime Policies

## Status

Accepted on 2026-03-14 as the normative runtime policy companion to ADR 0015.

## Sources

- `docs/architecture/adr/0015-ai-platform-layer.md`
- `docs/iso/lazy-investor-ai-plan.md`
- `docs/architecture/service-layer-runtime-policies.md`

## Scope

This document defines how AI capabilities are exposed, executed and governed inside the existing IRIS runtime model.

IRIS AI is not a parallel runtime. It is a capability layer on top of:

- canonical deterministic domains in `apps/*`;
- shared infrastructure in `core/*`;
- orchestration and workers in `runtime/*`;
- mode-aware HTTP surfaces in `api/*`.

## Capability Model

The current shared AI capability set is:

- `hypothesis_generate`
- `notification_humanize`
- `brief_generate`
- `explain_generate`

`hypothesis_evaluation` is not an AI capability. It remains a deterministic lifecycle path and must stay operable even when all real AI providers are offline.

## Provider and Prompt Governance

The following rules are normative:

- provider availability is resolved through the typed provider registry in `core.ai`;
- capability execution is allowed only when both capability policy and provider routing permit it;
- prompts may carry semantic defaults, style hints and safe rendering knobs;
- prompts may not control `base_url`, `endpoint`, auth headers, auth tokens or provider enablement;
- execution results must preserve `requested_provider` and `actual_provider` traceability;
- language is resolved by execution contract, not by provider defaults or prompt heuristics.

## Mode/Profile Matrix

The runtime matrix is:

| Surface | `full` | `local` | `ha_addon` / `HA_EMBEDDED` |
| --- | --- | --- | --- |
| hypothesis read surfaces | yes | yes | yes |
| hypothesis generation trigger | yes | yes | no |
| hypothesis evaluation job trigger | yes | yes | no public trigger |
| AI insight streams | yes | yes | no |
| control-plane AI admin | yes | yes | no |
| notification read surfaces | yes | yes | yes |
| brief read surfaces | yes | yes | selected cached reads only |
| brief generation trigger | yes | yes | no |
| explanation read surfaces | yes | yes | yes |
| explanation generation trigger | yes | yes | no |

The matrix is enforced through the same mode-aware router assembly and capability catalog used by the rest of the HTTP surface.

## Failure Domains

IRIS AI execution operates in three states:

- `healthy`: a real provider is configured, capability policy is enabled and validation runs normally;
- `degraded`: execution uses an explicit deterministic degraded strategy and this must remain auditable;
- `offline`: no real provider is available and generation capability must not pretend to succeed.

Operational consequences:

- read surfaces remain observable when generation is offline;
- deterministic evaluation paths continue to run;
- runtime must emit explicit unavailable or skipped results instead of silent pseudo-success;
- heuristic logic is never presented as a peer provider.

## Worker Isolation

Heavy AI execution must never sit on shared analytical worker lanes.

The current policy is:

- control-plane dispatching remains independent of AI execution;
- hypothesis generation uses its own dedicated workers and leaves deterministic evaluation separate;
- notification event humanization uses dedicated notification workers;
- brief and explanation generation run as tracked async jobs, not as synchronous analytical reads;
- AI outages must not block canonical signal, prediction, portfolio or market-structure flows.

## Operator Surface

AI operator/admin surfaces are part of the existing control-plane model.

The control-plane admin surface owns:

- AI provider catalog;
- AI capability state catalog;
- AI prompt catalog;
- editable prompt CRUD for DB-managed prompt families.

Code-managed prompt families remain visible in the operator catalog but are not mutable through HTTP admin APIs.

## Definition of Compliance

IRIS AI runtime is compliant with this policy only when:

- capability availability is resolved by provider registry plus runtime policy;
- router assembly, worker registration and scheduler paths use the same capability model;
- prompt, task, provider and degraded strategy remain explicitly separated;
- output validation is enforced before persisted artifacts are accepted;
- AI admin surfaces stay inside the existing control-plane model;
- no product-layer rename is introduced without a separate ownership decision.
