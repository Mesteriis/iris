# План реализации кастомного компонента IRIS для Home Assistant

## 1. Цель компонента

Разработать custom integration iris для Home Assistant, которая:

- автоматически обнаруживает IRIS через zeroconf
- подключается к IRIS по HTTP + WebSocket
- получает от IRIS bootstrap metadata
- валидирует совместимость версий и протокола
- загружает entity catalog, command catalog, collections catalog, dashboard schema
- динамически materialize-ит допустимые HA entities
- хранит bulk state во внутреннем runtime store
- принимает live updates по WebSocket
- отправляет команды обратно в IRIS
- создаёт dashboard IRIS в Home Assistant

## 2. Границы v1

### Входит в v1

- HACS-compatible custom component
- zeroconf discovery
- config flow
- HTTP bootstrap client
- WebSocket session
- runtime store
- dynamic entity materialization from catalog
- command bridge
- operation tracking
- dashboard schema consumption
- compatibility/version check
- submodule integration в основной repo
- CI / pre-commit / compatibility guards

### Не входит в v1

- addon packaging
- auto-install integration с backend
- entity-per-asset promoted mode
- визуальный редактор dashboard
- сложная offline-синхронизация
- multi-user permission model
- arbitrary frontend component engine

## 3. Репозиторная модель

### Отдельный репозиторий интеграции

Репозиторий компонента:

```
git@github.com:Mesteriis/ha-integration-iris.git
```

### Подключение в основной IRIS repo

Путь submodule:

```
ha/integration/custom_components/iris
```

### В основном repo обязательно

- `.gitmodules`
- README секция про submodule
- `ha/compatibility.yaml`
- CI checkout with submodules
- pre-commit checks для compatibility и protocol drift

## 4. Структура custom component

Рекомендуемая структура:

```
custom_components/iris/
  __init__.py
  manifest.json
  const.py
  config_flow.py
  diagnostics.py

  client.py
  websocket_client.py
  bootstrap.py
  versioning.py

  catalog.py
  entity_factory.py
  entity_registry_sync.py

  store.py
  subscriptions.py
  command_bus.py
  operations.py

  sensor.py
  binary_sensor.py
  button.py
  switch.py
  select.py
  event.py

  dashboard.py
  services.yaml
  strings.json
  translations/
    en.json

  models/
    __init__.py
    bootstrap.py
    catalog.py
    commands.py
    dashboard.py
    websocket.py
    state.py
```

## 5. manifest.json

### Должно быть

- domain: "iris"
- name: "IRIS"
- config_flow: true
- version
- zeroconf
- documentation
- issue_tracker
- codeowners
- зависимости, если реально нужны

### Zeroconf

IRIS должен обнаруживаться по:

```
_iris._tcp.local.
```

### Примерная идея для manifest

```json
{
  "domain": "iris",
  "name": "IRIS",
  "config_flow": true,
  "version": "0.1.0",
  "zeroconf": ["_iris._tcp.local."],
  "documentation": "https://github.com/Mesteriis/ha-integration-iris",
  "issue_tracker": "https://github.com/Mesteriis/ha-integration-iris/issues",
  "codeowners": ["@Mesteriis"]
}
```

## 6. Discovery и pairing

### 6.1 zeroconf discovery

Integration должна поддерживать:

- async_step_zeroconf
- async_step_user

### 6.2 Поток подключения

#### Через zeroconf

1. HA видит _iris._tcp.local.
2. запускает async_step_zeroconf
3. integration получает:
   - host
   - port
   - instance_id
   - version
   - protocol_version
4. делает bootstrap запрос
5. проверяет совместимость
6. создаёт config entry

#### Через manual setup

1. пользователь вводит URL / token
2. integration вызывает bootstrap
3. валидирует backend
4. создаёт config entry

## 7. Bootstrap contract

Integration должна использовать backend endpoint:

```
/api/v1/ha/bootstrap
```

### Из bootstrap получать

- instance_id
- display_name
- version
- protocol_version
- catalog_version
- mode
- minimum_ha_integration_version
- recommended_ha_integration_version
- catalog_url
- dashboard_url
- ws_url

## 8. Проверка совместимости

### Обязательная логика

На этапе config flow / startup integration обязана проверить:

- совместим ли protocol_version
- не ниже ли backend требует версию integration
- не устарела ли schema/contract
- не подключается ли integration к неподдерживаемому mode

### Поведение при несовместимости

- config entry не создаётся
- пользователю показывается понятная ошибка
- никаких "полу-подключённых" состояний

### Отдельный модуль

Сделать versioning.py, где будет:

- parsing version
- compatibility rules
- error messages

## 9. HTTP client

Нужен client.py для HTTP-запросов.

### Что должен уметь

- get_health()
- get_bootstrap()
- get_catalog()
- get_dashboard()
- get_operation(operation_id) как fallback
- возможно get_diagnostics()

### Не надо

Не превращать HTTP client в основной источник live state.
Основной поток состояния — через WebSocket.

## 10. WebSocket client

Нужен websocket_client.py.

### Обязанности

- connect / reconnect
- hello/welcome handshake
- subscribe
- ping/pong
- receive runtime messages
- send command_execute
- передавать updates в runtime store

### Поддерживаемые входящие сообщения

- welcome
- entity_state_changed
- state_patch
- collection_snapshot
- collection_patch
- operation_update
- catalog_changed
- dashboard_changed
- event_emitted
- system_health

### Поддерживаемые исходящие

- hello
- subscribe
- unsubscribe
- command_execute
- ping

## 11. Runtime store

Это одна из самых важных частей.

### Задача store

Хранить:

- connection state
- bootstrap metadata
- catalog snapshot
- dashboard schema
- entity states
- collections
- active operations
- last system health
- local sync timestamps

### Почему store важен

Потому что:

- не всё должно жить в entity
- не всё нужно писать в state attributes
- bulk-данные должны жить отдельно

### Что хранить как collections

Минимум:

- assets.snapshot
- portfolio.snapshot
- predictions.snapshot
- integrations.snapshot

## 12. Catalog-driven materialization

### Главное правило

Integration не должна заранее знать список entity.

Она materialize-ит только то, что приходит из backend catalog.

### Нужны модули

- catalog.py
- entity_factory.py
- entity_registry_sync.py

### Что они делают

**catalog.py**

- загрузка и валидация catalog
- хранение parsed model

**entity_factory.py**

- по записи из catalog создаёт нужный класс entity

**entity_registry_sync.py**

- сравнивает старый и новый catalog
- добавляет новые сущности
- обновляет metadata
- deprecated сущности не удаляет агрессивно

## 13. Поддерживаемые платформы v1

Нужно поддержать:

- sensor
- binary_sensor
- button
- switch
- select
- event

### Отдельно важно

Не делать sensor-per-coin по умолчанию.

**Bulk asset данные:**

- не materialize-ить автоматически как отдельные entity
- держать их в collections/store
- показывать через dashboard

## 14. Entity strategy

### Какие entity реально нужны в v1

Стабильные, компактные, automation-friendly.

**system**

- connection
- runtime mode
- integration health
- active assets count
- hot assets count

**portfolio**

- total value
- open positions
- available capital

**settings / controls**

- notifications enabled
- sync button
- market refresh button
- default timeframe select

**event**

- доменные event relay в HA event model

## 15. Command bridge

Нужен command_bus.py.

### Задачи

- взять command definition из catalog
- отправить command_execute
- сопоставить request_id
- сохранить operation_id
- отследить lifecycle через operation_update

### Минимум поддержать команды

- asset.add
- asset.remove
- portfolio.sync
- market.refresh
- telegram.start_auth
- telegram.confirm_auth
- news.connect_source
- news.disconnect_source

## 16. Operations tracking

Нужен operations.py.

### Что хранить

- operation_id
- source command
- status
- progress
- message
- timestamps

### Поведение

- immediate ack приходит быстро
- выполнение отслеживается через websocket
- ошибки красиво показываются пользователю

## 17. Dashboard layer

Нужен dashboard.py.

### Подход

Dashboard должен строиться на основе server-driven schema, а не быть жёстко захардкоженным.

### В v1

Достаточно:

1. создать отдельный dashboard IRIS
2. загрузить dashboard schema
3. создать базовые views:
   - Overview
   - Assets
   - Portfolio
   - Integrations
   - System

### Важно

На первом этапе не пытаться делать супер-умный full UI builder.
Сначала — стабильное применение backend schema.

## 18. Services в HA

В services.yaml описать user-facing actions.

Минимум:

- refresh market
- sync portfolio
- add asset
- remove asset
- start telegram auth
- confirm telegram auth

Но источник истины всё равно backend catalog

services.yaml — не для дублирования доменной логики, а для интеграции в UX HA.

## 19. Диагностика

Нужен diagnostics.py.

### Что показывать

- backend instance_id
- backend version
- protocol_version
- catalog_version
- websocket connected
- last health status
- supported capabilities
- integration version

Это сильно упростит дебаг.

## 20. User-local overrides

Integration должна уважать локальные настройки HA и не перетирать их при refresh catalog.

### Не перетирать

- custom names
- area assignment
- disabled by user
- локальные dashboard rearrangements, если будут позже

Backend задаёт только defaults.

Это важно.

## 21. Reconnect behavior

WebSocket соединение должно быть устойчивым.

Нужно реализовать

- reconnect loop
- backoff
- повторный hello
- повторный subscribe
- при reconnect — refresh state if needed
- если пришёл catalog_changed после reconnect — перезапросить catalog

## 22. Ошибки и UX

Нужно сделать человеческие ошибки для:

- protocol version mismatch
- backend unavailable
- websocket auth failed
- invalid bootstrap response
- command not available
- integration version too old
- catalog parse error

Это реально важно, иначе всё будет "Unknown error".

## 23. Тестирование

### Unit tests

Нужно покрыть:

- bootstrap parsing
- version compatibility rules
- catalog parsing
- entity factory
- command ack handling
- operation update transitions
- websocket message parsing

### Integration tests

Нужно покрыть:

- zeroconf flow
- config flow user setup
- bootstrap + compatibility
- websocket hello/welcome
- subscribe flow
- catalog-driven materialization
- catalog_changed re-sync
- collection updates
- command execution flow

### Contract tests

Очень желательно:

- mock backend bootstrap response
- mock catalog
- mock dashboard schema
- проверка, что integration понимает текущий protocol v1

## 24. CI для integration repo

Нужны джобы:

1. **Basic quality**
   - lint
   - tests
   - manifest validation

2. **Protocol compatibility**
   - проверка against mock bootstrap/catalog
   - сверка protocol_version

3. **Release sanity**
   - version field
   - required files
   - HACS-friendly structure

## 25. Pre-commit для integration repo

Добавить:

- format/lint
- json/yaml validation
- manifest checks
- protocol metadata checks
- запрет случайно ломать required structure

## 26. Связь с основным IRIS repo

Так как integration — submodule, надо договориться о workflow.

### Когда backend меняет protocol

Обязательно:

- обновить protocol docs
- обновить compatibility metadata
- при необходимости обновить integration repo
- обновить submodule ref в основном repo

### В основном repo

Добавить guard, что:

- если меняются backend HA bridge контракты
- а ha/compatibility.yaml не изменён
- CI/хук ругается

## 27. Файл совместимости

В основном repo рекомендую:

```
ha/compatibility.yaml
```

### Примерная идея

```yaml
protocol_version: 1

backend:
  minimum_version: "2026.03.14"

integration:
  repository: "git@github.com:Mesteriis/ha-integration-iris.git"
  minimum_version: "0.1.0"
  recommended_version: "0.1.0"
```

И integration должна сверять runtime bootstrap против своей версии.

## 28. Этапы реализации

### Этап 1 — Skeleton

- repo structure
- manifest
- constants
- config flow skeleton
- HTTP client skeleton
- WebSocket skeleton

### Этап 2 — Bootstrap + compatibility

- bootstrap models
- version checks
- config flow validation
- diagnostics basics

### Этап 3 — Runtime session

- websocket handshake
- subscribe/unsubscribe
- reconnect
- ping/pong

### Этап 4 — Catalog-driven entity model

- catalog parser
- entity factory
- registry sync
- initial entity platforms

### Этап 5 — Store + collections

- runtime store
- collection snapshot/patch handling
- state updates

### Этап 6 — Commands + operations

- command bus
- operation lifecycle
- HA services exposure

### Этап 7 — Dashboard

- dashboard schema loading
- initial dashboard creation
- basic views rendering

### Этап 8 — Hardening

- better errors
- reconnect corner cases
- deprecated entity behavior
- diagnostics
- contract tests

## 29. Definition of Done

Custom component считается готовым для v1, когда:

- [ ] ставится как HACS-compatible custom integration
- [ ] поддерживает manual setup и zeroconf discovery
- [ ] валидирует bootstrap и версии
- [ ] открывает websocket session
- [ ] получает catalog от backend
- [ ] materialize-ит сущности без hardcoded списка
- [ ] хранит collections отдельно от entity state
- [ ] умеет вызывать команды и отслеживать operations
- [ ] создает базовый dashboard из backend schema
- [ ] проходит CI и contract tests
- [ ] корректно работает с submodule-моделью в основном repo

## 30. Самые тонкие места, которые нельзя запороть

1. **Не хардкодить backend entity list в integration**
   Иначе вся идея server-driven catalog развалится.

2. **Не пытаться запихнуть bulk-данные в giant sensor attributes**
   Это будет боль для HA.

3. **Не делать polling главным транспортом**
   Он может быть только fallback/debug, не основа.

4. **Не удалять исчезнувшие entity агрессивно**
   Нужен lifecycle-aware sync.

5. **Не смешать dashboard schema и entity catalog**
   Это две разные модели.

6. **Не делать integration вторым backend**
   Логика — в IRIS, адаптация — в HA.

## 31. Рекомендуемый первый спринт

Я бы начал вот с такого набора задач:

### Sprint 1

- создать отдельный repo integration
- подключить submodule
- manifest + config_flow skeleton
- bootstrap endpoint client
- version compatibility checker
- websocket hello/welcome
- runtime store skeleton

### Sprint 2

- catalog parser
- entity factory
- sensor/binary_sensor/button/select
- registry sync
- collection store

### Sprint 3

- command bus
- operations
- dashboard schema loader
- basic IRIS dashboard
- diagnostics
- CI / pre-commit
