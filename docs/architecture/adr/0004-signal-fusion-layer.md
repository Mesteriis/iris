# ADR 0004: Signal Fusion Layer

## Status

**Accepted**

## Context

Рыночные сигналы могут противоречить друг другу.

**Например:**

- паттерн говорит BUY
- режим рынка говорит HOLD
- cross-market сигнал говорит SELL

Нужен слой агрегации сигналов.

## Decision

IRIS вводит Signal Fusion Engine.

**Fusion слой:**

- читает последние группы сигналов
- взвешивает их с учётом контекста
- разрешает конфликты
- генерирует unified market decision

Результат записывается в:

- market_decisions

## Consequences

**Плюсы:**

- единая рыночная позиция
- более устойчивые решения

**Минусы:**

- fusion логика может стать слишком сложной
- требуется explainability
