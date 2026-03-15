# IRIS Home Assistant Integration

Documentation for the IRIS and Home Assistant integration.

## Document Map

| Priority | Document | Role |
|---|----------|------|
| Spec | [Protocol Specification](protocol-specification.md) | **Authoritative** HTTP/WebSocket contract, payloads, lifecycle, compatibility |
| Note | [Architecture Notes](notes/index.md) | Non-normative architectural overviews and explanatory material |
| Archive | [Historical rollout artifacts](archive/index.md) | Completed plans, backlog material, and progress docs for the implemented integration |

## Authority Order

1. [Protocol Specification](protocol-specification.md) defines the public contract.
2. [Architecture Notes](notes/index.md) provide context and overview, but do not override the spec.
3. Archived rollout documents are useful only as implementation history and do not override the spec.

## Quick Start

```text
┌─────────────┐     WebSocket      ┌──────────────────┐
│    IRIS     │ <---------------> │ Home Assistant   │
│   Backend   │                   │   Integration    │
└─────────────┘                   └──────────────────┘
```

## Key Concepts

- **Server-driven** — IRIS is the source of truth for entities, commands, and dashboard definitions
- **Event-driven** — synchronization happens through push/WebSocket, without polling
- **Materialization** — Home Assistant creates entities dynamically from the backend catalog
- **Submodule** — the integration lives in a separate repository as a git submodule

## Versions

- **Protocol v1** — current protocol version
- **Backend** — IRIS `2026.03.14+`
- **HA Integration** — `0.1.0+`

## Links

- [HACS Repository](https://github.com/Mesteriis/ha-integration-iris)
- [IRIS Backend](https://github.com/Mesteriis/iris)
