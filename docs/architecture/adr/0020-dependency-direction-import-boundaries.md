# ADR 0020: Dependency Direction Rules and Import Boundaries

## Status

**Accepted**

## Date

2026-02-10

## Context

IRIS использует domain-oriented package structure:

iris.api

iris.apps.<domain>

iris.core

iris.runtime

Каждый домен в iris.apps организован по слоям:

api

application

domain

infrastructure

contracts

Без формального определения направления зависимостей даже аккуратная структура быстро деградирует:

api начинает содержать orchestration

domain начинает импортировать SQLAlchemy models

один домен начинает ходить в repositories другого домена

contracts начинают зависеть от transport или ORM

core превращается в мусорный shared bucket

Поэтому архитектура должна явно определить:

кто имеет право импортировать кого

какие зависимости допустимы

какие зависимости запрещены

какие границы контролируются линтером и CI

Decision

IRIS использует однонаправленную модель зависимостей.

Главный принцип:

зависимости направлены внутрь к более стабильным и более абстрактным слоям.

Более внешний слой может зависеть от более внутреннего.
Более внутренний слой не должен зависеть от более внешнего.

Canonical Dependency Direction

Внутри домена допустимое направление такое:

api -> application -> domain

infrastructure -> domain

infrastructure -> application.contracts допускается только там, где это нужно для реализации persistence / adapter mapping

application -> contracts допускается

api -> contracts допускается

domain -> contracts запрещено, кроме отдельно разрешённых truly domain-owned contracts, но по умолчанию запрещено

Layer Intent
domain

Самый стабильный слой предметной логики.

Содержит:

entities

value objects

policies

domain events

enums

domain exceptions

Domain не знает о transport, ORM, framework, API, cache, external integrations.

application

Слой use cases и orchestration.

Содержит:

commands

queries

application services

orchestration logic

transaction coordination

Application использует domain и contracts, но не должен зависеть от transport details.

api

Transport adapter layer.

Содержит:

routes

request parsing

response serialization

dependency wiring

error mapping

localization rendering

API не должен содержать бизнес-логику и не должен напрямую работать с ORM.

infrastructure

Слой реализации технических адаптеров.

Содержит:

ORM models

repositories

query implementations

cache adapters

external service adapters

integration clients

Infrastructure реализует зависимости, определённые application/domain, но не управляет бизнес-правилами.

contracts

Typed boundary objects.

Содержит:

command DTO

response DTO

read models

event payload contracts

Contracts должны быть максимально лёгкими и стабильными.

Allowed Dependencies Inside a Domain
api may import

application

contracts

domain only for stable enums/exceptions when necessary, but preferably through application or contracts

iris.core

application may import

domain

contracts

iris.core

domain may import

only iris.core modules that are explicitly designated as domain-safe

standard library

internal same-layer domain modules

infrastructure may import

domain

contracts

application interfaces / protocols / ports

iris.core

contracts may import

standard library

pydantic / typing / tiny shared primitives

iris.core only if extremely lightweight and stable

Contracts must not import domain services, infrastructure models, or transport code.

Forbidden Dependencies Inside a Domain
domain must not import

api

application

infrastructure

ORM models

repositories

framework-specific request/response objects

cache clients

external SDKs unless explicitly wrapped as domain-safe abstractions, which should be rare

application must not import

api

FastAPI request/response classes

ORM session management details unless abstracted

transport-layer serializers

api must not import

infrastructure ORM models

raw repositories directly if application layer exists for the same use case

business rules embedded in endpoints

contracts must not import

api

application.services

infrastructure

ORM models

transport framework types

Cross-Domain Dependency Rules

Домен не должен импортировать внутренности другого домена.

Разрешено импортировать другой домен только через:

contracts

explicitly declared public facades

rare shared abstractions moved to iris.core

Forbidden Cross-Domain Imports

Запрещено:

iris.apps.<other_domain>.api.*

iris.apps.<other_domain>.infrastructure.*

iris.apps.<other_domain>.repositories.*

iris.apps.<other_domain>.models.*

iris.apps.<other_domain>.application.services.* напрямую, если это не публичный facade

Cross-Domain Interaction Principle

Если одному домену нужен другой домен, он должен зависеть не от его внутренностей, а от одного из вариантов:

public contract

public application facade

shared event contract

shared abstraction in iris.core, если это действительно platform-level concern

Core Rules

iris.core является shared kernel, но не мусорным контейнером.

В core допускается размещать только:

config

logging

i18n

shared error base classes

telemetry primitives

platform-safe utility abstractions

foundational typing helpers

В core запрещено переносить туда код только ради обхода domain boundaries.

Core Dependency Policy

Все слои могут импортировать iris.core, но только его стабильные и layer-safe части.

Нельзя использовать core как backdoor для скрытой связанности между доменами.

Если модуль в core зависит от конкретного домена — он не должен находиться в core.

Runtime Rules

iris.runtime может импортировать:

iris.apps.*.application

iris.apps.*.contracts

selected infrastructure adapters where orchestration genuinely requires them

iris.core

Но доменные пакеты не должны зависеть от runtime.

Main Composition Rule

Composition root находится на верхнем уровне:

iris.main

transport bootstrap

runtime bootstrap

DI wiring

app assembly

Именно composition root связывает:

routes

application services

infrastructure implementations

runtime processes

Нижележащие слои не должны собирать приложение сами.

Dependency Matrix

Допустимая матрица внутри домена:

api -> application : allowed

api -> contracts : allowed

api -> domain : limited / discouraged

api -> infrastructure : discouraged, allowed only by explicit exception during migration

application -> domain : allowed

application -> contracts : allowed

application -> infrastructure : forbidden, except through abstractions/protocol boundaries

domain -> application : forbidden

domain -> api : forbidden

domain -> infrastructure : forbidden

domain -> contracts : forbidden by default

infrastructure -> domain : allowed

infrastructure -> contracts : allowed

infrastructure -> application : allowed only for ports/protocols/interfaces, not concrete orchestration flows

infrastructure -> api : forbidden

contracts -> domain : forbidden

contracts -> application : forbidden

contracts -> infrastructure : forbidden

contracts -> api : forbidden

Ports and Protocols Rule

Если application нуждается в реализации из infrastructure, зависимость должна идти через порт, protocol или interface, объявленный в application или в специальном stable boundary module.

Пример:

application/ports/market_data_reader.py

infrastructure/repositories/sql_market_data_reader.py

Application знает контракт, infrastructure знает реализацию.

ORM Isolation Rule

ORM модели должны жить только в infrastructure.

Они не должны утекать в:

domain

contracts

api

Domain entities и ORM models — не одно и то же.

Transport Isolation Rule

FastAPI, HTTP, SSE, WebSocket, request/response objects должны жить только в api и composition root.

Они не должны появляться в:

domain

application

contracts

Localization Boundary Rule

Localization должна выполняться на boundary слоях:

api

UI

integrations rendering layer

Domain и application не должны генерировать пользовательский текст.

Exceptions Policy
domain exceptions

Определяют предметный смысл ошибки.

application exceptions

Определяют orchestration/use-case failures.

api error mapping

Преобразует исключения в transport-safe responses и localized messages.

API не должен прокидывать сырые framework-specific exceptions в домен, а домен не должен знать о transport error shape.

Temporary Migration Exceptions

Во время рефакторинга допускаются временные нарушения только если:

они задокументированы

помечены TODO с owner

имеют срок удаления

не маскируются под целевую архитектуру

Временные исключения не считаются новым стандартом.

CI Enforcement

Архитектурные ограничения должны по возможности проверяться автоматически.

Рекомендуется использовать:

import-linter

deptry

ruff

custom architecture checks

CI должен постепенно начать проверять:

domain не импортирует infrastructure

contracts не импортируют ORM / API

cross-domain imports идут только через contracts или approved facades

src.* отсутствует в продуктовом коде

relative imports глубже .. отсутствуют

Consequences

Преимущества:

реальные, а не декоративные bounded contexts

предсказуемая архитектура зависимостей

меньше скрытой связанности

проще рефакторить и тестировать

легче подключить автоматический архитектурный контроль в CI

Недостатки:

потребуется дисциплина при добавлении новых модулей

часть legacy-кода придётся мигрировать

иногда потребуется создавать дополнительные ports/contracts вместо “быстрого прямого импорта”

Эти издержки считаются приемлемыми.

Result

IRIS использует строгую модель dependency direction, где:

зависимости направлены к более стабильным слоям

домен изолирован от transport и infrastructure

cross-domain связи контролируются

core не используется как обходной путь

архитектурные границы могут быть проверены автоматически

## See also

- [ADR 0019: Package Structure and Import Rules](0019-package-structure-import-rules.md) — структура пакетов
- [ADR 0002: Persistence Architecture](0002-persistence-architecture.md) — инфраструктурный слой
- [ADR 0009: Signals Service/Engine Split](0009-canonical-signals-service-engine-split.md) — пример разделения слоёв
