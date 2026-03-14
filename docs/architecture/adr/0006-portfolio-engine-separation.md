# ADR 0006: Portfolio Engine Separation

## Status

**Accepted**

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

**Плюсы:**

- чёткое разделение анализа и действий
- безопасное управление капиталом

**Минусы:**

- дополнительный слой архитектуры
