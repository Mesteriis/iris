# ADR 0001: Event-Driven Runtime Architecture

## Status

**Accepted**

## Date

2025-01-15

## Context

IRIS выполняет сложную аналитическую обработку рыночных данных:

- ingestion свечей
- вычисление индикаторов
- детекция паттернов
- построение рыночных режимов
- cross-market корреляции
- генерация сигналов
- fusion сигналов
- принятие инвестиционных решений
- управление портфелем

Наивная архитектура выполняла бы всё через:

- cron jobs
- синхронные пайплайны
- периодические batch вычисления

Такой подход плохо масштабируется и плохо восстанавливается после ошибок.

## Decision

IRIS использует event-driven runtime pipeline.

**Пайплайн:**

```
candle_closed
  → indicator_updated
  → analysis_requested
  → pattern_detected
  → decision_generated
  → portfolio_actions
```

Каждый этап реализован как независимый worker.

Workers обмениваются событиями через Redis Streams.

## Consequences

### Positive

- независимость подсистем
- устойчивость к падениям
- возможность горизонтального масштабирования
- простая повторная обработка событий

### Negative

- увеличивается сложность runtime
- требуется хорошая observability

## See also

- [ADR 0003: Control Plane for Event Routing](0003-control-plane-event-routing.md) — динамическая маршрутизация событий
- [ADR 0009: Signals Service/Engine Split](0009-canonical-signals-service-engine-split.md) — сервисная оркестрация
