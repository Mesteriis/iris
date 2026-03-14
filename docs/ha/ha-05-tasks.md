# IRIS HA Custom Integration

## Epic / Task Breakdown

---

## Epic 0 — Repo and delivery setup

### Цель

Подготовить репозиторий интеграции и связать его с основным IRIS repo через submodule.

### Tasks

#### 0.1. Создать и подготовить repo ha-integration-iris

- создать структуру HACS-compatible custom integration
- **важно:** репозиторий должен содержать корень с `custom_components/iris/`, НЕ вложенный слой
- добавить базовый README
- добавить LICENSE, если нужен
- определить initial version 0.1.0

#### 0.2. Перевести ha/integration/custom_components/iris в git submodule

- **исправить путь submodule:** `ha/integration/ha-integration-iris` (НЕ `ha/integration/custom_components/iris`, иначе путь задвоится)
- удалить текущую папку из индекса основного repo
- подключить submodule на git@github.com:Mesteriis/ha-integration-iris.git
- зафиксировать .gitmodules

#### 0.3. Обновить README основного IRIS repo

- добавить раздел про HA integration
- описать submodule workflow
- добавить команды clone/init/update
- описать связь backend ↔ integration через versioned protocol

#### 0.4. Добавить compatibility metadata

- создать ha/compatibility.yaml
- описать protocol_version
- описать minimum/recommended integration version
- описать repo source integration

#### 0.5. Настроить CI checkout c submodules

- добавить recursive checkout
- проверить наличие submodule файлов
- добавить отдельный job под integration

#### 0.6. Добавить pre-commit/guard checks в основной repo

- проверка .gitmodules
- проверка ha/compatibility.yaml
- guard на protocol drift

### Definition of Done

- [ ] integration repo существует
- [ ] submodule подключён
- [ ] README обновлён
- [ ] compatibility metadata добавлен
- [ ] CI видит submodule

---

## Epic 1 — HACS custom integration skeleton

### Цель

Поднять минимальный каркас custom integration.

### Tasks

#### 1.1. Создать структуру custom_components/iris

- `__init__.py`
- `manifest.json`
- `const.py`
- `strings.json`
- `translations/en.json`

#### 1.2. Подготовить manifest.json

- domain
- name
- config_flow
- version
- zeroconf
- documentation
- issue_tracker
- codeowners

#### 1.3. Добавить базовый config_flow.py

- async_step_user
- skeleton для async_step_zeroconf
- placeholder validation flow

#### 1.4. Добавить базовый entry setup

- инициализация integration через config entry
- использование `ConfigEntry.runtime_data` для typed runtime data
- `async_unload_entry` и `entry.async_on_unload` для cleanup

#### 1.5. Подготовить diagnostics.py skeleton

- basic config entry diagnostics hook

### Definition of Done

- [ ] integration ставится как custom component
- [ ] HA видит domain iris
- [ ] config flow зарегистрирован

---

## Epic 2 — Discovery and bootstrap

### Цель

Сделать автообнаружение IRIS и bootstrap-подключение.

### Tasks

#### 2.1. Реализовать zeroconf discovery

- обработка _iris._tcp.local.
- чтение discovery metadata
- связка с async_step_zeroconf

#### 2.2. Реализовать manual setup flow

- форма ввода URL / auth token
- валидация backend

#### 2.3. Реализовать HTTP bootstrap client

- get_health()
- get_bootstrap()
- базовая error handling логика

#### 2.4. Реализовать parsing bootstrap response

- models для instance metadata
- capability flags
- ws/catalog/dashboard URLs

#### 2.5. Реализовать unique instance binding

- использовать instance_id как unique_id config entry
- исключить дублирующее подключение одного IRIS instance
- **при повторном zeroconf discovery того же instance_id — обновлять host/port**

#### 2.6. Реализовать HA-native flows

- async_step_reauth для смены auth/token
- async_step_reconfigure для смены host/port
- ConfigEntryAuthFailed для auth-проблем
- ConfigEntryNotReady для временных проблем

### Definition of Done

- [ ] manual setup работает
- [ ] zeroconf discovery работает
- [ ] config entry создаётся после успешного bootstrap

---

## Epic 3 — Version and protocol compatibility

### Цель

Не допускать запуска интеграции с несовместимым backend.

### Tasks

#### 3.1. Создать versioning.py

- parse integration version
- parse backend version
- parse protocol version

#### 3.2. Реализовать compatibility rules

- сравнение protocol_version
- сравнение minimum_ha_integration_version
- сравнение recommended_ha_integration_version

#### 3.3. Реализовать user-facing errors

- unsupported protocol
- integration too old
- backend too old
- unsupported mode

#### 3.4. Добавить compatibility check в config flow

- проверять bootstrap до создания entry

#### 3.5. Добавить compatibility check на startup

- защита от upgrade drift после уже созданного entry

### Definition of Done

- [ ] несовместимая версия блокирует setup
- [ ] пользователь получает понятную ошибку

---

## Epic 4 — WebSocket session and live transport

### Цель

Сделать основной live transport через WebSocket.

### Tasks

#### 4.1. Реализовать websocket_client.py

- connect
- disconnect
- reconnect
- send message
- receive loop

#### 4.2. Реализовать hello/welcome handshake

- отправка hello
- обработка welcome
- валидация protocol/capabilities

#### 4.3. Реализовать subscribe/unsubscribe

- подписка на entities
- подписка на collections
- подписка на operations/catalog/dashboard

#### 4.4. Реализовать ping/pong

- keepalive
- idle connection health

#### 4.5. Реализовать reconnect behavior

- exponential backoff
- повторный handshake
- повторный subscribe

### Definition of Done

- [ ] integration стабильно держит websocket session
- [ ] reconnect работает без ручного вмешательства

---

## Epic 5 — Runtime store

### Цель

Создать внутренний store для state, collections и metadata.

### Tasks

#### 5.1. Реализовать store.py

- connection state
- bootstrap metadata
- catalog snapshot
- dashboard snapshot
- entity states
- collections
- operation states

#### 5.2. Реализовать state access API

- get entity state
- get collection
- get operation
- update state path

#### 5.3. Реализовать collection handling

- full snapshot replace
- patch apply
- timestamps / version markers

#### 5.4. Реализовать internal update signaling

- чтобы entity/platform layer получал обновления из store

#### 5.5. Реализовать resync and gap handling

- отслеживать projection_epoch и sequence
- детектировать gaps в последовательности
- при gap или смене epoch — trigger full resync
- использовать /api/v1/ha/state endpoint

### Definition of Done

- [ ] store держит актуальный runtime state
- [ ] websocket updates корректно попадают в store

---

## Epic 6 — Catalog models and parsing

### Цель

Загрузить server-driven catalog и валидировать его.

### Tasks

#### 6.1. Создать модели catalog

- entity definition
- collection definition
- command definition
- view definition

#### 6.2. Реализовать catalog.py

- fetch catalog
- parse catalog
- validate required fields
- хранить catalog_version

#### 6.3. Реализовать catalog_changed handling

- по событию делать refetch
- синхронизировать materialized state

#### 6.4. Реализовать compatibility-safe parsing

- tolerate unknown optional fields
- аккуратно падать на critical schema errors

### Definition of Done

- [ ] integration понимает backend catalog
- [ ] catalog refresh работает

---

## Epic 7 — Dynamic entity materialization

### Цель

Создавать HA entities из backend catalog, а не из hardcoded списка.

### Tasks

#### 7.1. Создать entity_factory.py

- mapping platform -> entity class
- factory по entity definition

#### 7.2. Создать entity_registry_sync.py

- сравнение старого и нового catalog
- добавление новых entity
- обновление metadata
- обработка deprecated/hidden status

#### 7.3. Реализовать platform support v1

- sensor
- binary_sensor
- button
- switch
- select
- event

**Примечание:** platform `number` НЕ входит в v1 (удалён из spec)

#### 7.4. Реализовать entity base classes

- чтение state из store
- чтение attributes из store
- availability
- icon/device_class/category support

#### 7.6. Реализовать stable unique_id

- формула: `unique_id = f"{instance_id}:{entity_key}"`
- это обеспечивает стабильность при catalog refresh

#### 7.7. Реализовать translation_key для entity names

- использовать translation_key + has_entity_name = True
- name из catalog как fallback/display hint
- поддержка i18n

#### 7.5. Реализовать lifecycle-aware behavior

- active
- deprecated
- hidden
- removed без агрессивного удаления

### Definition of Done

- [ ] integration materialize-ит entities из catalog
- [ ] ручного списка сущностей в коде нет

---

## Epic 8 — Entity state updates

### Цель

Научить materialized entity жить от store и live updates.

### Tasks

#### 8.1. Реализовать обработку entity_state_changed

- обновление state/attributes
- refresh entity state in HA

#### 8.2. Реализовать обработку state_patch

- patch по runtime path
- обновление зависимых entity

#### 8.3. Реализовать availability / connection degradation

- если websocket упал, сущности корректно уходят в unavailable при нужной политике

#### 8.4. Реализовать compact attributes strategy

- не тащить giant bulk payload в entity attributes

### Definition of Done

- [ ] entity в HA live обновляются из websocket state

---

## Epic 9 — Collections and bulk data strategy

### Цель

Поддержать большие динамические данные без sensor-per-coin модели.

### Tasks

#### 9.1. Реализовать collection store

- assets.snapshot
- portfolio.snapshot
- predictions.snapshot
- integrations.snapshot

#### 9.2. Реализовать обработку collection_snapshot

- full replace

#### 9.3. Реализовать обработку collection_patch

- upsert/remove/update по path

#### 9.4. Реализовать API доступа к collections для dashboard layer

#### 9.5. Явно исключить auto-materialization per asset

- не создавать entity на каждую монету по умолчанию

### Definition of Done

- [ ] bulk state хранится в collections/store
- [ ] нет засорения HA сущностями по активам

---

## Epic 10 — Command bridge

### Цель

Сделать двустороннее управление из HA в IRIS.

### Tasks

#### 10.1. Реализовать command_bus.py

- отправка command_execute
- correlation через request_id
- command ack handling

#### 10.2. Реализовать command catalog binding

- команда доступна только если объявлена backend
- command availability учитывает mode/features

#### 10.3. Реализовать HA services mapping

- **generic service:** `iris.execute_command` — выполняет любую команду из backend catalog
- **curated wrapper services:**
  - `iris.sync_portfolio`
  - `iris.refresh_market`
  - `iris.start_telegram_auth`
  - `iris.add_asset`
  - `iris.remove_asset`

**Регистрация:** в `async_setup` (не в config flow), чтобы сервисы были доступны независимо от entry state

#### 10.4. Реализовать UI-friendly error handling

- command not available
- invalid payload
- backend rejected

### Definition of Done

- [ ] команды можно запускать из HA
- [ ] integration не хардкодит произвольные команды мимо backend catalog

---

## Epic 11 — Operations tracking

### Цель

Поддержать lifecycle долгих команд.

### Tasks

#### 11.1. Реализовать operations.py

- operation model
- status lifecycle
- progress/message storage

#### 11.2. Реализовать command_ack handling

- сохранять operation_id
- связывать с исходным request

#### 11.3. Реализовать operation_update handling

- queued
- in_progress
- completed
- failed
- cancelled

#### 11.4. Реализовать user feedback

- service result
- notification/logging/debug visibility

### Definition of Done

- [ ] async команды корректно отслеживаются через operation lifecycle

---

## Epic 12 — Event relay into HA

### Цель

Прокинуть доменные события IRIS в Home Assistant event layer.

### Tasks

#### 12.1. Реализовать обработку event_emitted

- нормализовать event type
- fire HA events where appropriate

#### 12.2. Определить минимальный v1 event set

- decision updates
- prediction outcomes
- portfolio actions
- integration/auth events

#### 12.3. Зафиксировать naming policy

- понятный префикс и consistent event contract

### Definition of Done

- [ ] HA automation layer может реагировать на события IRIS

---

## Epic 13 — Dashboard schema consumption

### Цель

Создавать IRIS dashboard в HA из backend schema.

### Tasks

#### 13.1. Реализовать dashboard.py

- fetch dashboard schema
- parse views/sections/widgets

#### 13.2. Реализовать basic dashboard creation

- создать dashboard IRIS
- initial views:
  - Overview
  - Assets
  - Portfolio
  - Integrations
  - System

#### 13.3. Реализовать widget binding к collections/store

- summary widgets
- tables/lists
- status blocks
- actions blocks

#### 13.4. Реализовать dashboard_changed handling

- refetch schema
- аккуратный update strategy

### Definition of Done

- [ ] integration создает usable IRIS dashboard из backend schema **(только если backend advertising capabilities.dashboard = true)**

> **Note:** Dashboard является capability-gated фичей v1+. Основной transport/catalog/command контур НЕ зависит от dashboard готовности.

---

## Epic 14 — Diagnostics and observability

### Цель

Сделать интеграцию дебагабельной.

### Tasks

#### 14.1. Реализовать diagnostics.py

- backend instance_id
- backend version
- protocol_version
- catalog_version
- integration version
- websocket connected
- capabilities

#### 14.2. Реализовать internal debug logging

- bootstrap
- websocket lifecycle
- catalog refresh
- command execution
- operation updates

#### 14.3. Реализовать clear error surfaces

- config flow errors
- runtime warnings
- protocol mismatch messages

### Definition of Done

- [ ] по диагностике можно понять, почему integration не работает

---

## Epic 15 — Local override safety

### Цель

Не ломать пользовательские настройки HA при catalog refresh.

### Tasks

#### 15.1. Зафиксировать правила override safety

- не перетирать custom names
- не перетирать area assignment
- не включать обратно вручную disabled entity

#### 15.2. Реализовать safe sync behavior

- catalog update меняет only backend-owned defaults
- user-local overrides уважаются

### Definition of Done

- [ ] обновление catalog не ломает локальную настройку HA

---

## Epic 16 — CI, tests, quality gates

### Цель

Нормально стабилизировать integration repo.

### Tasks

#### 16.1. Настроить lint/test pipeline

- lint
- unit tests
- integration tests

#### 16.2. Добавить protocol contract tests

- mock bootstrap
- mock catalog
- mock dashboard
- mock websocket messages
- **shared canonical fixtures (одновременно для backend и integration):**
  - `fixtures/v1/bootstrap.ok.json`
  - `fixtures/v1/catalog.minimal.json`
  - `fixtures/v1/ws.command_ack.accepted.json`
  - `fixtures/v1/ws.command_ack.rejected.json`
  - `fixtures/v1/ws.collection_snapshot.replace.json`
  - `fixtures/v1/ws.resync_required.json`

#### 16.3. Добавить manifest / repo sanity checks

- required files
- version field
- HACS-friendly structure

#### 16.4. Настроить pre-commit

- json/yaml validation
- formatting/lint
- protocol metadata checks

### Definition of Done

- [ ] integration repo проходит CI
- [ ] contract drift ловится тестами

---

## Epic 17 — Main repo integration guards

### Цель

Стабилизировать связку backend repo ↔ integration submodule.

### Tasks

#### 17.1. Добавить submodule presence check в main repo CI

- submodule checkout recursive
- наличие обязательных файлов integration

#### 17.2. Добавить compatibility check

- validate ha/compatibility.yaml
- compare expected protocol version

#### 17.3. Добавить drift guard

- если изменились backend HA bridge contracts, а compatibility metadata не обновлена — CI валится

#### 17.4. Обновить docs workflow

- как обновлять submodule ref
- как обновлять protocol metadata
- как релизить совместимые версии

### Definition of Done

- [ ] main repo контролирует совместимость с submodule integration

---

## Suggested milestone breakdown

### Milestone 1 — Foundation

**Включает:**

- Epic 0
- Epic 1
- Epic 2
- Epic 3

**Результат:**

- repo setup
- submodule
- config flow
- bootstrap
- version compatibility

### Milestone 2 — Live connectivity

**Включает:**

- Epic 4
- Epic 5
- Epic 6

**Результат:**

- websocket session
- runtime store
- catalog loading

### Milestone 3 — Dynamic HA model

**Включает:**

- Epic 7
- Epic 8
- Epic 9

**Результат:**

- dynamic entities
- live state updates
- collections strategy

### Milestone 4 — Bidirectional control

**Включает:**

- Epic 10
- Epic 11
- Epic 12

**Результат:**

- command bridge
- operation tracking
- HA events

### Milestone 5 — UX and hardening

**Включает:**

- Epic 13
- Epic 14
- Epic 15
- Epic 16
- Epic 17

**Результат:**

- dashboard
- diagnostics
- CI/quality
- compatibility safety

---

## Самые важные first issues

Если совсем приземлённо, я бы первым пакетом создал такие issue:

1. Create HACS-compatible iris integration skeleton
2. Move ha/integration/custom_components/iris to git submodule
3. Implement IRIS bootstrap client and config flow validation
4. Add protocol/version compatibility checks
5. Implement WebSocket hello/welcome session
6. Create runtime store for entities, collections, operations
7. Implement catalog parser and dynamic entity factory
8. Add collection snapshot/patch handling
9. Implement command execution bridge
10. Add operation lifecycle tracking
11. Implement dashboard schema loading
12. Add diagnostics and contract tests
13. Wire compatibility and submodule checks into main repo CI

---

## Что я бы сделал прямо самым первым

Без шуток, вот такой порядок даст максимум пользы:

### Шаг 1
Submodule + repo skeleton + README + compatibility file

### Шаг 2
Bootstrap + config flow + version checks

### Шаг 3
WebSocket session + runtime store

### Шаг 4
Catalog parser + dynamic entities

### Шаг 5
Commands + operations

### Шаг 6
Dashboard + hardening