# IRIS ↔ Home Assistant Integration

Документация по интеграции IRIS с Home Assistant.

## Содержание

| # | Документ | Описание |
|---|----------|----------|
| SPEC | [Протокол](ha-02-protocol-spec.md) | **Authoritative** — HTTP endpoints, WebSocket, сообщения, контракты |
| 01 | [ADR: Архитектура](adr-0001-ha-integration-architecture.md) | Non-normative overview |
| 03 | [Backend план](ha-03-backend-plan.md) | План реализации HA Bridge на стороне IRIS |
| 04 | [HACS интеграция](ha-04-hacs-integration-plan.md) | План реализации custom integration для Home Assistant |
| 05 | [Задачи](ha-05-tasks.md) | Epic-ы и задачи для реализации |
| 06 | [Прогресс](ha-06-progress.md) | Текущий статус этапов, прогресс и ближайшие шаги |

> **Приоритет:** В случае расхождений между документами, **spec является источником истины**.

## Быстрый старт

```
┌─────────────┐     WebSocket      ┌─────────────┐
│     IRIS    │ ◄────────────────► │ Home Assistant │
│   Backend   │                    │  Integration  │
└─────────────┘                    └─────────────┘
```

## Ключевые концепции

- **Server-driven** — IRIS является источником истины для entities, commands, dashboard
- **Event-driven** — синхронизация через push/WebSocket, без polling
- **Materialization** — HA создаёт entities динамически из backend catalog
- **Submodule** — интеграция живёт в отдельном репозитории как git submodule

## Версии

- **Protocol v1** — текущая версия протокола
- **Backend** — IRIS 2026.03.14+
- **HA Integration** — 0.1.0+

## Ссылки

- [HACS Repository](https://github.com/Mesteriis/ha-integration-iris)
- [IRIS Backend](https://github.com/Mesteriis/iris)
