# ADR 0007: Cross-Market Intelligence

## Status

**Accepted**

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

**Плюсы:**

- более контекстные сигналы
- выявление лидерских активов

**Минусы:**

- сложность расчётов
- необходимость корректной калибровки
