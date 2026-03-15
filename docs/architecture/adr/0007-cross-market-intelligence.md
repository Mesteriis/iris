# ADR 0007: Cross-Market Intelligence

## Status

**Accepted**

## Date

2025-01-21

## Context

Крипторынок сильно связан.

**Примеры:**

- BTC → ETH
- ETH → altcoins
- sector rotation

Игнорирование этих связей ухудшает сигналы.

## Decision

IRIS вводит Cross-Market Intelligence Layer.

**Система:**

- вычисляет корреляции
- определяет лидеров рынка
- фиксирует lag между активами
- усиливает сигналы follower активов

Данные сохраняются в:

- coin_relations

## Consequences

### Positive

- более контекстные сигналы
- выявление лидерских активов

### Negative

- сложность расчётов
- необходимость корректной калибровки

## See also

- [ADR 0004: Signal Fusion Layer](0004-signal-fusion-layer.md) — fusion с другими сигналами
