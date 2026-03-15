# Open Source Guide

IRIS is being prepared for a public OSS workflow around the current repository and architecture model rather than around the older wiki structure.

## Repository Policies

- License: [LICENSE](https://github.com/Mesteriis/iris/blob/main/LICENSE)
- Contributions: [CONTRIBUTING.md](https://github.com/Mesteriis/iris/blob/main/CONTRIBUTING.md)
- Security reporting: [SECURITY.md](https://github.com/Mesteriis/iris/blob/main/SECURITY.md)
- Community expectations: [CODE_OF_CONDUCT.md](https://github.com/Mesteriis/iris/blob/main/CODE_OF_CONDUCT.md)

## Documentation Policy

IRIS documentation is split by purpose:

- `docs/architecture/` is for active architecture contracts, governance guidance, supporting notes, and historical architecture archive
- `docs/delivery/` is for active rollout plans, execution boards, and implementation audits
- `docs/home-assistant/` is for integration-specific protocol docs, explanatory notes, and historical integration archive
- `docs/_generated/` is for code-derived artifacts exported from CI/tooling

## Contribution Expectations

Contributors are expected to preserve the current structural contracts:

- backend layering stays `runtime -> apps -> core`
- active HTTP/API surfaces remain governed through committed snapshots
- service-layer changes respect orchestration vs analytical-engine separation
- docs must be updated when architecture or repository entrypoints change

## What To Read Before Large Changes

- [Architecture Overview](architecture/index.md)
- [ADR Index](architecture/adr/index.md)
- [Service Layer Runtime Policies](architecture/service-layer-runtime-policies.md)
- [Service Layer Performance Budgets](architecture/service-layer-performance-budgets.md)
- [Delivery](delivery/index.md)

## Notes

- Home Assistant protocol questions must defer to `docs/home-assistant/protocol-specification.md` over plan or progress documents.
- Generated docs under `docs/_generated/` should be refreshed whenever the governed HTTP surface changes.
