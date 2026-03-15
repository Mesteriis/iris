# ADR 0019: Package Structure, Import Rules, and Source Root Policy

## Status

**Accepted**

## Date

2026-02-01

## Context

IRIS является аналитической платформой с архитектурой, основанной на:

domain-oriented modules

bounded contexts

event-driven orchestration

layered architecture

strict separation of concerns

По мере роста проекта возникает риск:

хаотичной структуры пакетов

неявных зависимостей между доменами

появления "utility" файлов

сложных относительных импортов

смешивания инфраструктуры и доменной логики

Кроме того, текущая структура использует src как source root, что приводит к импортам вида:

from src.apps.signals.services import ...

Это связывает код с layout репозитория и ухудшает читаемость.

Поэтому требуется стандарт, который:

делает структуру проекта предсказуемой

делает зависимости между доменами явными

устраняет инфраструктурный namespace src из продуктового кода

закрепляет единый продуктовый namespace iris

Decision

IRIS использует единый продуктовый namespace iris.

Все продуктовые импорты должны начинаться с:

iris.*

src/ используется только как repository layout, но не является namespace продукта.

Source Root Policy

Repository layout:

backend/
  src/
    iris/

Пример:

backend/src/iris/apps/signals

Импорт:

from iris.apps.signals.application.services.build_signal_snapshot import ...

Запрещено:

from src.apps.signals ...

src является layout concern, а не частью runtime namespace.

Project Package Layout

Структура backend пакета:

iris/
  api/
  apps/
  core/
  runtime/
  main.py
Package Responsibilities
iris.api

HTTP / transport layer.

Содержит:

routers

dependencies

request mapping

response mapping

error translation

Бизнес логика здесь запрещена.

iris.apps

Bounded contexts.

Каждый домен системы реализуется как отдельный пакет.

Примеры:

iris.apps.signals
iris.apps.market_data
iris.apps.control_plane
iris.apps.settings
iris.core

Shared kernel платформы.

Содержит:

configuration

i18n

logging

error base classes

telemetry

shared utilities

core должен быть минимальным и стабильным.

iris.runtime

Infrastructure runtime:

workers

stream processors

schedulers

event loop orchestration

Domain Package Structure

Каждый домен в iris.apps должен следовать единой структуре.

apps/<domain>/
  api/
  application/
  domain/
  infrastructure/
  contracts/
Layer Responsibilities
api

Transport adapters.

Примеры:

routes.py
read_routes.py
write_routes.py
dependencies.py
error_mapping.py
application

Use cases и orchestration.

Содержит:

commands/
queries/
services/

Примеры файлов:

create_signal.py
activate_strategy.py
list_signals.py
refresh_market_data.py
domain

Чистая предметная модель.

Содержит:

entities.py
value_objects.py
events.py
exceptions.py
enums.py
policies/

Domain слой не зависит от инфраструктуры.

infrastructure

Persistence и интеграции.

Содержит:

models.py
repositories/
queries/
cache/
integrations/
contracts

Typed contracts между слоями.

Содержит:

commands.py
responses.py
read_models.py
events.py
File Naming Rules

Файл должен описывать конкретную ответственность.

Allowed
refresh_market_data.py
build_signal_snapshot.py
activate_strategy.py
signal_history_query.py
Forbidden
utils.py
helpers.py
common.py
misc.py
manager.py
processor.py
service.py

Такие имена считаются архитектурным запахом.

Avoid Tautological Naming

Путь уже содержит архитектурный слой.

Плохо:

application/services/signal_service.py
domain/models/domain_models.py

Хорошо:

application/services/build_signal_snapshot.py
domain/entities.py
Aggregator Files

Файлы типа:

repositories.py
schemas.py
models.py

допустимы только если:

они маленькие

содержат логически связанную группу объектов

При росте их необходимо разделять.

Import Rules
Within Same Domain

Разрешены relative imports.

Пример:

from .exceptions import SignalError
from ..contracts.read_models import SignalSummary
Cross-Domain Imports

Должны быть absolute imports.

Пример:

from iris.apps.market_data.contracts.read_models import MarketSnapshot

Запрещено:

from ...market_data.contracts import MarketSnapshot
Relative Import Depth

Relative imports глубже чем .. запрещены.

Разрешено:

.
..

Запрещено:

...
....
Cross-Domain Dependency Rules

Домен может импортировать другой домен только через public modules.

Разрешено:

contracts
public facades

Запрещено:

api
infrastructure
repositories
ORM models
private services

Пример плохого импорта:

from iris.apps.market_data.infrastructure.models import MarketModel
Core Imports

iris.core импортируется только абсолютными импортами.

from iris.core.config import settings
Test Imports

В тестах допускается дополнительная настройка import paths.

src может использоваться как source root в test environment.

Однако продуктовый код не должен использовать namespace src.

Architectural Goal

Структура проекта должна обеспечивать:

читаемость путей

явные границы доменов

минимальную связанность

простоту рефакторинга

масштабируемость архитектуры

Result

IRIS использует:

единый namespace iris

строгую структуру доменных пакетов

понятные имена файлов

контролируемые зависимости между доменами

предсказуемую систему импортов

Это обеспечивает устойчивость архитектуры при росте системы.

## See also

- [ADR 0020: Dependency Direction Rules and Import Boundaries](0020-dependency-direction-import-boundaries.md) — правила направления зависимостей
- [ADR 0002: Persistence Architecture](0002-persistence-architecture.md) — инфраструктурный слой
