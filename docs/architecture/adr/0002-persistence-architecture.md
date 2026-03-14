# ADR 0002: Persistence Architecture

## Status

**Accepted**

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

**Плюсы:**

- предсказуемые транзакции
- упрощение тестирования
- предотвращение N+1

**Минусы:**

- больше кода инфраструктуры
- требуется дисциплина при разработке
