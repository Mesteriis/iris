# ADR — Platform Maturity Additions for IRIS

## Status

**Accepted**

## Date

2026-03-01

## Context

IRIS уже выглядит как сильный инженерный продукт, но для перехода из состояния "хорошо собранная система" в состояние "зрелая платформа" ему не хватает нескольких системных слоёв.

Речь не о добавлении случайных функций, а о введении управляемых платформенных механизмов, которые делают систему предсказуемой, объяснимой, наблюдаемой и расширяемой.

Ниже зафиксирован набор из восьми обязательных направлений, которые должны дополнять существующую архитектуру без разрушения текущего ядра.

## Decision

### 1. Capability / Feature Registry ⏳

**Status:** Not started

**Описание**

Единый реестр возможностей системы, подключённых провайдеров, интеграций, режимов запуска и доступных функций.

**Зачем**

Чтобы frontend, backend, CLI, интеграции и Home Assistant не определяли доступность функций через разрозненные условия и скрытые проверки.

**Правила**

- capability должна быть оформлена как явный контракт
- источник истины должен быть один
- capability должна быть типизирована
- доступность функций должна определяться через registry, а не через произвольные if в коде
- registry должен учитывать режимы full, local, addon
- registry должен быть доступен через стабильный API и пригоден для UI

### 2. Health / Readiness / Diagnostics ⚠️

**Status:** Partially implemented — basic `/system/health` and source health endpoints exist, but health/readiness/diagnostics not fully separated

**Описание**

Слой проверки состояния системы и её зависимостей.

**Зачем**

Чтобы различать ситуацию "процесс жив" и ситуацию "система готова обслуживать реальные сценарии".

**Правила**

- разделять health, readiness, diagnostics
- отдельно проверять БД, кэш, брокер, фоновые воркеры, внешние провайдеры, HA-интеграции и ключевые внутренние пайплайны
- публичные ответы должны быть безопасными и минимальными
- расширенная диагностика должна быть доступна только в операторском контуре
- статусы зависимостей должны быть нормализованы
- ошибки зависимостей должны использовать единый error catalog

### 3. Job Control Plane ⚠️

**Status:** Partially implemented — TaskIQ used for background jobs, but unified control plane with standardized lifecycle, retry, cancel, progress not implemented

**Описание**

Единый слой управления фоновыми задачами, ingestion-пайплайнами, пересчётами и асинхронными операциями.

**Зачем**

Чтобы фоновые процессы перестали быть скрытой логикой и стали наблюдаемыми, управляемыми и документированными.

**Правила**

- каждая задача должна иметь идентификатор, тип, статус, correlation id и связанный контекст
- жизненный цикл задач должен быть стандартизирован
- должны поддерживаться retry, cancel, progress, timestamps и нормализованный error payload
- API управления задачами должен быть отделён от кода исполнения
- бизнес-логика не должна зависеть от конкретного transport/job-runner механизма
- все фоновые операции должны быть трассируемыми и аудируемыми

### 4. Audit Trail / Event Timeline ✅

**Status:** Implemented — EventRouteAuditLog in control_plane app with full audit trail

**Описание**

Нормализованный журнал значимых доменных событий и изменений состояния сущностей.

**Зачем**

Чтобы можно было восстановить последовательность действий, понять причину изменения состояния и объяснить поведение системы.

**Правила**

- фиксировать нужно не только ошибки, но и значимые доменные события
- audit trail не должен подменяться техническими логами
- каждое событие должно содержать actor, source, entity reference, timestamp и event type
- формулировки событий должны быть стабильны и пригодны для UI
- таймлайн должен строиться из нормализованных событий, а не из произвольных текстовых сообщений
- события должны быть пригодны и для внутреннего анализа, и для пользовательского объяснения

### 5. Unified Error Catalog ✅

**Status:** Implemented — PLATFORM_ERROR_REGISTRY in src/core/errors/catalog.py with error codes, message keys, severity, retryability, HTTP mapping

**Описание**

Единый каталог ошибок продукта с кодами, маппингом и правилами отображения.

**Зачем**

Чтобы убрать хаотичные строковые ошибки, упростить i18n, стабилизировать API-поведение и обеспечить единый контракт между backend, frontend и интеграциями.

**Правила**

- у каждой ошибки должен быть machine-readable code
- текст должен идти через i18n key
- отдельно хранить user-safe message и operator-facing details
- error catalog должен задавать severity, retryability и http mapping
- запрещено вводить новые ошибки вне каталога
- одна и та же причина сбоя должна давать один и тот же код в одинаковом контексте
- каталог ошибок должен использоваться также в jobs, integrations и HA flows

### 6. Policy / Rules Layer Lite ⚠️

**Status:** Partially implemented — AnomalyPolicyEngine exists in anomalies app, but general policy layer not implemented

**Описание**

Лёгкий слой правил, условий, ограничений и автоматических реакций системы.

**Зачем**

Чтобы сигналы, рекомендации, действия и автоматизации определялись декларативно, а не через размазанные захардкоженные условия.

**Правила**

- правило должно быть декларативным объектом, а не скрытым кодовым условием
- правило должно включать condition set, scope, cooldown и action binding
- должна быть поддержка dry-run и explain mode
- side effects не должны быть скрыты внутри вычисления условий
- правила должны быть тестируемыми изолированно
- правила должны быть пригодны для интеграции с Home Assistant и внутренними automation flows
- policy layer должен быть расширяемым, но не превращаться в тяжёлый BPM-движок

### 7. Explanation Layer ✅

**Status:** Implemented — Full explanations app with signal/decision explanation generation and storage

**Описание**

Слой объяснения решений, расчётов, сигналов и рекомендаций, формируемых системой.

**Зачем**

Чтобы аналитика и автоматизация не воспринимались как чёрный ящик и могли быть объяснены пользователю или оператору.

**Правила**

- каждое значимое решение должно иметь explanation contract
- explanation должно ссылаться на входные данные, время расчёта, факторы влияния и контекст
- explanation не должно быть сырым debug dump
- формулировки должны быть пригодны для UI, API и документации
- должен поддерживаться разный уровень детализации для user-facing и operator-facing представления
- explanation должно быть согласовано с policy layer, audit trail и error catalog

### 8. Config Governance ⚠️

**Status:** Partially implemented — pydantic-settings with schema-driven config exists, but effective config display and full precedence model not implemented

**Описание**

Управляемая, валидируемая и наблюдаемая система конфигурации.

**Зачем**

Чтобы поведение системы в режимах full, local, addon было предсказуемым, воспроизводимым и безопасным.

**Правила**

- конфигурация должна быть schema-driven
- должен быть понятен источник каждого значения
- секреты должны быть отделены от обычной конфигурации
- должна быть зафиксирована precedence model для env, file, defaults и runtime overrides
- система должна уметь показывать effective config без утечки sensitive data
- ошибки конфигурации должны выявляться как можно раньше
- конфигурация должна быть пригодна для операторской диагностики и CI-проверок

## Consequences

### Positive

- IRIS становится платформой, а не просто набором функций
- поведение системы становится предсказуемее
- упрощается поддержка нескольких режимов запуска
- frontend и интеграции получают стабильные контракты
- становится проще сопровождать jobs, интеграции и HA-сценарии
- улучшаются операционная наблюдаемость, дебаг и объяснимость
- снижается архитектурный долг от строковых ошибок, скрытых флагов и разрозненной конфигурации

### Negative

- увеличится объём контрактов и архитектурных артефактов
- часть текущих механизмов придётся нормализовать и унифицировать
- потребуются дополнительные тесты, документация и migration-проход по слоям
- реализация потребует дисциплины, иначе появятся дублирующие полу-решения

## Not in Scope

На данном этапе в это решение не входят:

- full enterprise RBAC
- multi-tenant architecture
- marketplace расширений
- тяжёлый visual automation builder
- event sourcing как базовая модель архитектуры
- избыточная микросервисная декомпозиция

## Summary

Приоритет должен быть не в наращивании случайного feature surface, а в создании платформенного каркаса вокруг уже существующих возможностей.

Эти восемь направлений формируют минимальный набор зрелости, после которого IRIS можно уверенно позиционировать как:

- наблюдаемую платформу
- объяснимую платформу
- управляемую платформу
- расширяемую платформу
- пригодную для интеграций и нескольких режимов запуска

## See also

- [ADR 0002: Persistence Architecture](architecture/adr/0002-persistence-architecture.md) — инфраструктурный слой
- [ADR 0003: Control Plane for Event Routing](architecture/adr/0003-control-plane-event-routing.md) — control plane
- [ADR 0016: Error Taxonomy Boundary Localization](architecture/adr/0016-error-taxonomy-boundary-localization.md) — unified error catalog
- [ADR 0017: Text Ownership Localization Scope](architecture/adr/0017-text-ownership-localization-scope.md) — i18n foundation

---

## Implementation Status (2026-03-15)

| # | Component | Status | Notes |
|---|-----------|--------|-------|
| 1 | Capability / Feature Registry | ⏳ Not started | |
| 2 | Health / Readiness / Diagnostics | ⚠️ Partial | `/system/health`, source health endpoints exist |
| 3 | Job Control Plane | ⚠️ Partial | TaskIQ used, unified control plane not implemented |
| 4 | Audit Trail / Event Timeline | ✅ Done | EventRouteAuditLog in control_plane |
| 5 | Unified Error Catalog | ✅ Done | PLATFORM_ERROR_REGISTRY in src/core/errors/ |
| 6 | Policy / Rules Layer Lite | ⚠️ Partial | AnomalyPolicyEngine exists |
| 7 | Explanation Layer | ✅ Done | Full explanations app |
| 8 | Config Governance | ⚠️ Partial | pydantic-settings, no effective config display |
