# ADR 0002: Persistence Architecture

## Status

**Accepted**

## Date

2025-01-16

## Context

В ранней версии проекта доступ к БД происходил напрямую из разных частей кода:

- API routes
- workers
- сервисы

Это приводило к:

- размазанным транзакциям
- N+1 запросам
- трудно тестируемому коду

## Decision

IRIS вводит стандартизированную persistence архитектуру.

**Правила:**

- Write side выполняется через **repositories**
- Read side выполняется через **query services**
- Transaction boundaries контролируются **Unit of Work**
- Read path использует immutable typed models
- Routes и workers не работают напрямую с AsyncSession

## Consequences

### Positive

- предсказуемые транзакции
- упрощение тестирования
- предотвращение N+1

### Negative

- больше кода инфраструктуры
- требуется дисциплина при разработке

## See also

- [ADR 0010: Caller Owns Commit Boundary](0010-caller-owns-commit-boundary.md) — владение транзакционной границей
- [ADR 0014: Side Effects Execute Post-Commit](0014-side-effects-post-commit-only.md) — безопасность записи
