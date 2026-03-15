# ADR 0004: Signal Fusion Layer

## Status

**Accepted**

## Date

2025-01-18

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

### Positive

- единая рыночная позиция
- более устойчивые решения

### Negative

- fusion логика может стать слишком сложной
- требуется explainability

## See also

- [ADR 0007: Cross-Market Intelligence](0007-cross-market-intelligence.md) — корреляционный анализ
- [ADR 0006: Portfolio Engine Separation](0006-portfolio-engine-separation.md) — исполнение решений
