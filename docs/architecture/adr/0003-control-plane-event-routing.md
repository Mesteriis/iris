# ADR 0003: Control Plane for Event Routing

## Status

**Accepted**

## Date

2025-01-17

## Context

В event-driven системах routing событий часто захардкожен:

- consumer groups
- topic subscriptions
- handler mapping

Это усложняет:

- экспериментирование
- staged rollout
- shadow routing
- runtime topology changes

## Decision

IRIS вводит control plane для управления маршрутизацией событий.

**Основные сущности:**

- event_definitions
- event_consumers
- event_routes
- topology_config_versions
- topology_drafts

Runtime dispatcher читает активную topology snapshot и направляет события соответствующим consumers.

## Consequences

### Positive

- гибкое управление routing
- возможность shadow processing
- безопасные изменения topology

### Negative

- дополнительная сложность runtime
- требуется контроль версии topology

## See also

- [ADR 0001: Event-Driven Runtime](0001-event-driven-runtime.md) — основа event pipeline
