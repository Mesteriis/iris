# Architecture Decision Records (ADR)

Коллекция ADR, описывающих ключевые архитектурные решения IRIS.

## Содержание

| # | ADR | Описание |
|---|-----|----------|
| 0001 | [Event-Driven Runtime](0001-event-driven-runtime.md) | Event-driven pipeline для обработки рыночных данных |
| 0002 | [Persistence Architecture](0002-persistence-architecture.md) | Стандартизированный доступ к БД через repositories и query services |
| 0003 | [Control Plane for Event Routing](0003-control-plane-event-routing.md) | Управление маршрутизацией событий через control plane |
| 0004 | [Signal Fusion Layer](0004-signal-fusion-layer.md) | Агрегация и разрешение конфликтов рыночных сигналов |
| 0005 | [Analytical Snapshot API Semantics](0005-analytical-snapshot-api-semantics.md) | Семантика freshness для аналитических API |
| 0006 | [Portfolio Engine Separation](0006-portfolio-engine-separation.md) | Разделение аналитики и портфельного управления |
| 0007 | [Cross-Market Intelligence](0007-cross-market-intelligence.md) | Учёт межрыночных корреляций |
| 0008 | [Research vs Production Runtime](0008-research-vs-production-runtime.md) | Разделение research и production слоёв |
| 0009 | [Signals Service/Engine Split](0009-signals-service-engine-split.md) | Canonical split between orchestration services and analytical engines |
| 0010 | [Caller Owns Commit Boundary](0010-caller-owns-commit-boundary.md) | Правило владения транзакционной границей |
| 0011 | [Analytical Engines Never Fetch](0011-analytical-engines-never-fetch.md) | Analytical engines do not perform IO |
| 0012 | [Services Return Domain Contracts](0012-services-return-domain-contracts.md) | Сервисы возвращают typed domain contracts |
| 0013 | [Async Classes for Orchestration](0013-async-classes-for-orchestration-pure-functions-for-analysis.md) | Async классы для orchestration, pure функции для аналитики |
| 0014 | [Side Effects Execute Post-Commit](0014-post-commit-side-effects-only.md) | Side effects выполняются только после коммита |
| 0015 | [Shared AI Platform Layer](0015-ai-platform-layer.md) | Общий AI platform layer с capability-aware provider registry и shared executor |

## Что такое ADR?

Architecture Decision Record (ADR) — документ, описывающий архитектурное решение и его контекст.

Формат ADR:
- **Status**: Proposed / Accepted / Deprecated / Superseded
- **Context**: проблема или ситуация, требующая решения
- **Decision**: принятое решение
- **Consequences**: последствия (плюсы и минусы)

## Ссылки

- [Service Layer Runtime Policies](../service-layer-runtime-policies.md)
- [Service Layer Performance Budgets](../service-layer-performance-budgets.md)
- [Complexity Guardrails](../complexity-guardrails.md)
- [Principal Engineering Checklist](../principal-engineering-checklist.md)
