# Open Source Guide

IRIS is being prepared for a public OSS workflow around the current repository and architecture model rather than around the older wiki structure.

## Repository Policies

- License: [LICENSE](https://github.com/Mesteriis/iris/blob/main/LICENSE)
- Contributions: [CONTRIBUTING.md](https://github.com/Mesteriis/iris/blob/main/CONTRIBUTING.md)
- Security reporting: [SECURITY.md](https://github.com/Mesteriis/iris/blob/main/SECURITY.md)
- Community expectations: [CODE_OF_CONDUCT.md](https://github.com/Mesteriis/iris/blob/main/CODE_OF_CONDUCT.md)

## Documentation Policy

IRIS documentation is split by purpose:

- `docs/architecture/` is for accepted architecture and governance guidance
- `docs/iso/` is for working plans, execution boards, and implementation audits
- `docs/_generated/` is for code-derived artifacts exported from CI/tooling
- `docs/reviews/` is for dated review snapshots and should not be treated as normative architecture

## Contribution Expectations

Contributors are expected to preserve the current structural contracts:

- backend layering stays `runtime -> apps -> core`
- active HTTP/API surfaces remain governed through committed snapshots
- service-layer changes respect orchestration vs analytical-engine separation
- docs must be updated when architecture or repository entrypoints change

## What To Read Before Large Changes

- [Architecture Overview](architecture.md)
- [ADR Index](architecture/adr/index.md)
- [Service Layer Runtime Policies](architecture/service-layer-runtime-policies.md)
- [Service Layer Performance Budgets](architecture/service-layer-performance-budgets.md)
- [Delivery And Audits](iso/index.md)

## Notes

- Review documents in `docs/reviews/` are useful context, but they are snapshots in time and may lag the implementation.
- Generated docs under `docs/_generated/` should be refreshed whenever the governed HTTP surface changes.
