# ADR 0005: Analytical Snapshot API Semantics

## Status

**Accepted**

## Context

Аналитические API отличаются от CRUD API.

**Ответы могут быть:**

- кэшированными
- вычисленными
- не абсолютно свежими

Без явного указания freshness клиенты могут ошибочно считать данные актуальными.

## Decision

Все аналитические ответы должны содержать metadata snapshot.

**Примеры:**

- generated_at
- freshness_class
- staleness_ms

HTTP ответы должны поддерживать:

- Cache-Control
- ETag
- Last-Modified
- deterministic 304 Not Modified

## Consequences

**Плюсы:**

- честная семантика аналитических данных
- возможность безопасного кеширования

**Минусы:**

- усложнение API контрактов
