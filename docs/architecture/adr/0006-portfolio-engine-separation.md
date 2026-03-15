# ADR 0006: Portfolio Engine Separation

## Status

**Accepted**

## Date

2025-01-20

## Context

Аналитические сигналы и реальные действия должны быть разделены.

Аналитика может быть неточной, но портфельные действия требуют строгих правил.

## Decision

IRIS вводит отдельный Portfolio Engine.

**Portfolio engine:**

- читает market decisions
- применяет риск-ограничения
- рассчитывает размер позиции
- генерирует portfolio actions

**Основные ограничения:**

- max position size
- max portfolio exposure
- risk adjustments

## Consequences

### Positive

- чёткое разделение анализа и действий
- безопасное управление капиталом

### Negative

- дополнительный слой архитектуры

## See also

- [ADR 0004: Signal Fusion Layer](0004-signal-fusion-layer.md) — источник сигналов
- [ADR 0012: Services Return Domain Contracts](0012-services-return-domain-contracts-not-transport.md) — паттерны сервисного слоя
