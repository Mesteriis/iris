# IRIS ↔ Home Assistant Protocol Specification

## Статус

**Draft v1**

> **Document Status**
> 
> This document is normative for IRIS ↔ Home Assistant protocol v1.
> 
> **Derived documents:**
> - `ha-03-backend-plan.md` — implementation guidance for IRIS backend
> - `ha-04-hacs-integration-plan.md` — implementation guidance for HA integration
> - `ha-05-tasks.md` — executable backlog
> - `adr-0001-ha-integration-architecture.md` — architecture overview / ADR-like note
> 
> If any derived document conflicts with this spec, this spec wins.

## Цель

Определить стабильный контракт между backend IRIS и custom integration Home Assistant, чтобы:

- IRIS оставался единственной точкой истины для entity catalog, command catalog, dashboard schema и runtime state
- HA integration оставалась тонким адаптером, а не вторым backend
- новые сущности, команды и view-модели могли добавляться без ручной синхронизации кода в двух местах
- двусторонняя связь работала через push/event-driven модель, без polling как основного механизма
- контракт можно было эволюционировать без ломания старых установок

---

## 1. Архитектурная модель

### 1.1 Роли сторон

#### IRIS

**Владеет:**

- runtime state
- доменными событиями
- entity catalog
- collection catalog
- command catalog
- dashboard schema
- operation lifecycle
- capability matrix

#### Home Assistant Integration

**Отвечает за:**

- discovery и pairing
- websocket session
- materialization entity в HA
- локальный runtime store
- отправку команд в IRIS
- применение dashboard schema в HA
- user-local overrides

---

## 2. Транспорт

### 2.1 Discovery

Discovery выполняется через zeroconf/mDNS.

**Service type:**

```
_iris._tcp.local.
```

**Required TXT records**

- instance_id
- version
- api_port
- ws_path
- mode
- catalog_version
- protocol_version

**Recommended TXT records**

- requires_auth
- display_name
- dashboard_supported
- commands_supported

### 2.2 HTTP API

HTTP используется для:

- первичного bootstrap
- получения catalog и dashboard schema
- fallback read endpoints
- health checks
- optional operation inspection

### 2.3 WebSocket

WebSocket является основным live transport для:

- runtime updates
- catalog changes
- command execution
- operation tracking
- collection patches

**Основной endpoint:**

```
/api/v1/ha/ws
```

---

## 3. Принципы протокола

### 3.1 Server-driven integration

IRIS всегда объявляет, что именно доступно для HA:

- какие entity можно создать
- какие collections доступны
- какие команды можно вызвать
- какие views должны быть показаны

HA не должна hardcode-ить каталог сущностей как источник истины.

### 3.2 Не всё является entity

Протокол разделяет:

- **entities** — materializable HA objects
- **collections** — крупные агрегированные наборы данных
- **commands** — вызываемые действия
- **views** — схема UI/dashboard

### 3.3 Backward compatibility

Все контракты должны поддерживать версионирование и мягкую эволюцию:

- новые поля можно добавлять
- удаление полей допустимо только через deprecated lifecycle
- entity нельзя резко убирать без migration path
- command rename должен сопровождаться replacement metadata

---

## 4. HTTP Endpoints

### 4.1 Health

```
GET /api/v1/ha/health
```

**Назначение:**

- первичная проверка живости
- проверка совместимости протокола
- проверка состояния bridge

**Пример ответа:**

```json
{
  "status": "ok",
  "instance_id": "iris-main-001",
  "version": "2026.03.14",
  "protocol_version": 1,
  "catalog_version": "2026.03.14",
  "mode": "full",
  "websocket_supported": true,
  "dashboard_supported": true
}
```

### 4.2 Bootstrap

```
GET /api/v1/ha/bootstrap
```

**Назначение:**

- единая стартовая точка для integration
- позволяет не делать 5 отдельных запросов при первом подключении

**Пример ответа:**

```json
{
  "instance": {
    "instance_id": "iris-main-001",
    "display_name": "IRIS Main",
    "version": "2026.03.14",
    "protocol_version": 1,
    "catalog_version": "2026.03.14",
    "mode": "full",
    "minimum_ha_integration_version": "0.1.0",
    "recommended_ha_integration_version": "0.1.0"
  },
  "capabilities": {
    "dashboard": true,
    "commands": true,
    "collections": true,
    "promoted_entities": false
  },
  "catalog_url": "/api/v1/ha/catalog",
  "dashboard_url": "/api/v1/ha/dashboard",
  "ws_url": "/api/v1/ha/ws"
}
```

**URL Resolution:**

All URLs in bootstrap response are **relative to the origin of the bootstrap request**. Clients MUST resolve them against the bootstrap endpoint origin (scheme + host + port).
```

### 4.3 Catalog

```
GET /api/v1/ha/catalog
```

**Назначение:**

- описание доступных entity
- описание collections
- описание commands
- описание lifecycle и compatibility

**Пример ответа:**

```json
{
  "catalog_version": "2026.03.14",
  "protocol_version": 1,
  "mode": "full",
  "entities": [],
  "collections": [],
  "commands": [],
  "views": []
}
```

### 4.4 Dashboard Schema

```
GET /api/v1/ha/dashboard
```

**Назначение:**

- server-driven схема dashboard/layout/cards/views

**Пример ответа:**

```json
{
  "version": 1,
  "slug": "iris",
  "title": "IRIS",
  "views": []
}
```

### 4.5 Optional Operation Status

```
GET /api/v1/ha/operations/{operation_id}
```

**Назначение:**

- fallback или debug read по операции

**Пример ответа:**

```json
{
  "operation_id": "op_123",
  "status": "completed",
  "result": {
    "message": "Asset added"
  }
}
```

---

## 5. Catalog Schema

### 5.1 Top-level structure

```json
{
  "catalog_version": "2026.03.14",
  "protocol_version": 1,
  "mode": "full",
  "entities": [],
  "collections": [],
  "commands": [],
  "views": []
}
```

### 5.2 Entity Definition

**Обязательные поля**

- entity_key
- platform
- name
- state_source

**Рекомендуемые поля**

- icon
- category
- default_enabled
- availability
- since_version
- deprecated_since
- replacement
- entity_registry_enabled_default
- device_class
- unit_of_measurement

**Пример:**

```json
{
  "entity_key": "system.connection",
  "platform": "binary_sensor",
  "name": "IRIS Connection",
  "state_source": "system.connection",
  "icon": "mdi:lan-connect",
  "category": "diagnostic",
  "default_enabled": true,
  "device_class": "connectivity",
  "since_version": "2026.03.14",
  "deprecated_since": null,
  "replacement": null
}
```

### 5.3 Supported HA Platforms

v1 поддерживает:

- sensor
- binary_sensor
- switch
- button
- select
- number
- event

Расширение списка в будущем допустимо только через protocol bump или capability flag.

### 5.4 Entity Availability

**Пример:**

```json
{
  "modes": ["full", "local", "ha_addon"],
  "requires_features": ["portfolio"],
  "status": "active"
}
```

Где:

- **modes** — в каких режимах сущность допустима
- **requires_features** — какие доменные возможности должны быть активны
- **status** — active | deprecated | hidden | removed

### 5.5 Collection Definition

Collection — это не HA entity, а runtime data model для UI/store.

**Обязательные поля:**

- collection_key
- kind
- transport

**Пример:**

```json
{
  "collection_key": "assets.snapshot",
  "kind": "mapping",
  "transport": "websocket",
  "dashboard_only": true,
  "since_version": "2026.03.14"
}
```

**Возможные kind:**

- mapping
- list
- table
- timeline
- summary

### 5.6 Command Definition

**Обязательные поля:**

- command_key
- name
- kind

**Рекомендуемые:**

- input_schema
- returns
- availability
- since_version
- deprecated_since
- replacement

**Пример:**

```json
{
  "command_key": "asset.add",
  "name": "Add Asset",
  "kind": "action",
  "input_schema": {
    "type": "object",
    "properties": {
      "symbol": {
        "type": "string"
      }
    },
    "required": ["symbol"]
  },
  "returns": "operation",
  "since_version": "2026.03.14"
}
```

**Возможные kind:**

- action
- flow
- toggle
- selection
- refresh
- admin

### 5.7 View Definition

View — серверное описание части dashboard.

**Пример:**

```json
{
  "view_key": "overview",
  "title": "Overview",
  "kind": "dashboard_view",
  "sections": [
    {
      "section_key": "market_summary",
      "title": "Market Summary",
      "widgets": [
        {
          "widget_key": "hot_assets",
          "kind": "table",
          "source": "assets.snapshot"
        }
      ]
    }
  ]
}
```

---

## 6. Runtime State Model

### 6.1 State Source Convention

Поле state_source в entity definition указывает путь в runtime state.

**Пример:**

```
system.connection
portfolio.summary.available_capital
market.summary.hot_assets_count
settings.default_timeframe
```

### 6.2 Collection Source Convention

Коллекции обновляются либо полным snapshot, либо patch-сообщениями.

---

## 7. WebSocket Protocol

### 7.1 Session Lifecycle

#### Этап 1 — connect

HA открывает websocket:

```
ws://host:port/api/v1/ha/ws
```

#### Этап 2 — hello

HA отправляет hello message.

**Пример:**

```json
{
  "type": "hello",
  "protocol_version": 1,
  "client": {
    "name": "home_assistant",
    "version": "1.0.0"
  },
  "instance_id": "optional-known-instance-id"
}
```

#### Этап 3 — welcome

IRIS отвечает welcome.

**Пример:**

```json
{
  "type": "welcome",
  "protocol_version": 1,
  "instance": {
    "instance_id": "iris-main-001",
    "version": "2026.03.14",
    "mode": "full",
    "catalog_version": "2026.03.14"
  },
  "capabilities": {
    "commands": true,
    "collections": true,
    "dashboard": true
  }
}
```

#### Этап 4 — subscribe

HA отправляет список интересующих потоков.

**Пример:**

```json
{
  "type": "subscribe",
  "entities": ["*"],
  "collections": ["assets.snapshot", "portfolio.snapshot"],
  "operations": true,
  "catalog": true,
  "dashboard": true
}
```

### 7.2 Client → Server Messages

#### hello

Устанавливает сессию.

#### subscribe

Подписка на изменения.

#### unsubscribe

Снятие подписки.

**Пример:**

```json
{
  "type": "unsubscribe",
  "collections": ["assets.snapshot"]
}
```

#### command_execute

Выполнение команды.

**Пример:**

```json
{
  "type": "command_execute",
  "command": "asset.add",
  "payload": {
    "symbol": "BTC"
  },
  "request_id": "req_001"
}
```

#### ping

**Пример:**

```json
{
  "type": "ping",
  "timestamp": "2026-03-14T10:00:00Z"
}
```

#### ack_event

Опциональное подтверждение клиентом.

### 7.3 Server → Client Messages

#### welcome

Ответ на hello.

#### pong

Ответ на ping.

#### entity_state_changed

Изменение состояния entity.

**Пример:**

```json
{
  "type": "entity_state_changed",
  "entity_key": "system.connection",
  "state": true,
  "attributes": {
    "last_seen": "2026-03-14T10:00:05Z"
  },
  "timestamp": "2026-03-14T10:00:05Z"
}
```

#### state_patch

Patch по runtime state.

**Пример:**

```json
{
  "type": "state_patch",
  "path": "portfolio.summary.available_capital",
  "value": 12450.75,
  "timestamp": "2026-03-14T10:00:10Z"
}
```

#### collection_snapshot

Полный snapshot коллекции.

```json
{
  "type": "collection_snapshot",
  "collection_key": "assets.snapshot",
  "data": {
    "BTC": {
      "decision": "BUY",
      "confidence": 0.82
    }
  },
  "timestamp": "2026-03-14T10:00:12Z"
}
```

#### collection_patch

Частичное обновление коллекции.

```json
{
  "type": "collection_patch",
  "collection_key": "assets.snapshot",
  "op": "upsert",
  "path": "BTC",
  "value": {
    "decision": "STRONG_BUY",
    "confidence": 0.91
  },
  "timestamp": "2026-03-14T10:00:15Z"
}
```

#### catalog_changed

Сигнализирует, что надо перезапросить catalog.

```json
{
  "type": "catalog_changed",
  "catalog_version": "2026.03.15",
  "timestamp": "2026-03-14T10:00:20Z"
}
```

#### dashboard_changed

Сигнализирует, что надо перезапросить dashboard schema.

#### operation_update

Обновление состояния операции.

```json
{
  "type": "operation_update",
  "operation_id": "op_123",
  "status": "in_progress",
  "progress": 50,
  "message": "Synchronizing portfolio",
  "timestamp": "2026-03-14T10:00:30Z"
}
```

#### event_emitted

Доменно-ориентированное уведомление для HA events. Использует полный Event Envelope.

```json
{
  "type": "event_emitted",
  "event_type": "decision_generated",
  "event_id": "evt_001",
  "source": "decision_engine",
  "payload": {
    "coin": "BTC",
    "decision": "BUY",
    "confidence": 0.82
  },
  "timestamp": "2026-03-14T10:00:40Z"
}
```

#### system_health

Техническое состояние bridge/runtime.

#### command_ack

Ответ на command_execute.

**Positive ack:**

```json
{
  "type": "command_ack",
  "request_id": "req_002",
  "operation_id": "op_456",
  "accepted": true
}
```

**Negative ack:**

```json
{
  "type": "command_ack",
  "request_id": "req_002",
  "accepted": false,
  "error": {
    "code": "command_not_available",
    "message": "Command is not available in current mode",
    "details": {
      "command": "portfolio.sync",
      "mode": "local"
    }
  },
  "retryable": false
}
```

---

## 8. Event Envelope

Все runtime events, проходящие в HA, должны использовать единый envelope.

```json
{
  "event_type": "decision_generated",
  "event_id": "evt_001",
  "source": "decision_engine",
  "timestamp": "2026-03-14T10:00:40Z",
  "payload": {}
}
```

**Обязательные поля:**

- event_type
- event_id
- source
- timestamp
- payload

---

## 7.x Delivery and Resynchronization Semantics

All state-bearing websocket messages MUST include:

- `projection_epoch`: string (monotonic version identifier)
- `sequence`: integer (monotonic within epoch)

**State-bearing messages:**

- entity_state_changed
- state_patch
- collection_snapshot
- collection_patch
- catalog_changed
- dashboard_changed
- operation_update
- system_health

**Rules:**

- `sequence` is strictly monotonic within a `projection_epoch`
- client MUST detect sequence gaps
- if a gap is detected, or `projection_epoch` changes, client MUST trigger full resync
- full resync MUST use `/api/v1/ha/state` or refetch bootstrap + catalog + required collections, as defined by capability

---

## 9. Command Execution Contract

### 9.1 Request

```json
{
  "type": "command_execute",
  "command": "portfolio.sync",
  "payload": {},
  "request_id": "req_002"
}
```

### 9.2 Immediate Ack

IRIS должен быстро вернуть ack, не держа websocket request-response до конца job.

```json
{
  "type": "command_ack",
  "request_id": "req_002",
  "operation_id": "op_456",
  "accepted": true
}
```

### 9.3 Final Result

Итог уходит через operation_update.

---

## 10. Operation Lifecycle

**Статусы операций:**

- accepted
- queued
- in_progress
- completed
- failed
- cancelled

**Пример жизненного цикла:**

```
command_execute
  -> command_ack
  -> operation_update: queued
  -> operation_update: in_progress
  -> operation_update: completed
```

---

## 11. Entity Materialization Rules in HA

### 11.1 Общие правила

HA integration должна:

- materialize только те сущности, которые пришли в entities
- не materialize collections как entities по умолчанию
- сохранять local registry snapshot
- сравнивать catalog version
- уметь re-sync после catalog_changed

### 11.2 Поведение при исчезновении сущности

Если entity больше нет в catalog:

- не удалять её мгновенно
- сначала пометить unavailable/deprecated
- при наличии replacement показать migration path
- физическая очистка — отдельным явным действием

### 11.3 User overrides

Локальные пользовательские настройки HA не должны перетираться catalog refresh-ом:

- custom name
- area assignment
- disabled by user
- dashboard placement override

---

## 12. Collections Strategy

Collections нужны для динамических bulk-данных, например:

- assets snapshot
- market summary map
- portfolio snapshot
- prediction journal
- integrations status

Они не должны автоматически превращаться в сотни HA entities.

**Default strategy:**

- collections хранятся во внутреннем store integration
- dashboard/cards читают их из store
- entity-per-asset допускается только как future promoted mode

---

## 13. Dashboard Contract

### 13.1 Server-driven Dashboard

IRIS отдает только декларативную схему:

- dashboard slug
- views
- sections
- widgets
- data source bindings

HA integration отвечает за:

- превращение схемы в Lovelace/panel representation
- локальные user customizations
- сохранение dashboard instance

### 13.2 Minimal widget kinds v1

- summary
- table
- timeline
- status
- actions
- chart_placeholder
- list

---

## 14. Security Model

### 14.1 Required headers for HTTP commands

Для HTTP-команд должны поддерживаться:

- X-IRIS-Actor
- X-IRIS-Access-Mode

Дополнительно при необходимости:

- X-IRIS-Reason
- X-IRIS-Control-Token

### 14.2 WebSocket auth

v1 допустимо использовать один из режимов:

- token in query/header during upgrade
- pre-authorized local trusted mode
- short-lived session token from bootstrap

Финальная реализация выбирается отдельно, но протокол должен предусматривать auth-required path.

---

## 15. Versioning Policy

### 15.1 Protocol Version

protocol_version меняется только при breaking changes транспортного или message-уровня.

### 15.2 Catalog Version

catalog_version — monotonic opaque string (SHOULD use content hash or monotonic counter, NOT date string).

catalog_version меняется при любом изменении entity/command/view/collection catalog.

### 15.3 Backend Version

version — обычная версия IRIS runtime.

---

## 16. Error Contract

Все transport-level ошибки должны иметь единый формат.

```json
{
  "error": {
    "code": "command_not_available",
    "message": "Command is not available in current mode",
    "details": {
      "command": "portfolio.sync",
      "mode": "ha_addon"
    }
  }
}
```

**Рекомендуемые коды:**

- invalid_message
- unsupported_protocol_version
- unauthorized
- forbidden
- command_not_available
- invalid_payload
- catalog_outdated
- entity_not_found
- operation_not_found
- internal_error

---

## 17. Minimal v1 Scope

В первую версию должны войти:

### Со стороны IRIS

- HA bridge consumer поверх текущего HA consumer из event bus
- websocket gateway
- /ha/health
- /ha/bootstrap
- /ha/catalog
- /ha/dashboard
- command execution adapter
- event envelope normalization
- catalog_changed сигнал

### Со стороны HA integration

- zeroconf discovery
- config flow
- websocket session
- entity materializer
- runtime collection store
- command bridge
- basic dashboard creation
- catalog re-sync

---

## 18. Non-goals for v1

В v1 не включать:

- HA add-on packaging
- complex promoted entity-per-coin mode
- full bidirectional dashboard editor
- offline queueing
- advanced per-user permissions inside HA
- server-driven arbitrary frontend components
- auto-install custom integration from IRIS

---

## 19. Open Questions

Нужно отдельно дожать и зафиксировать:

- ~~где именно живет auth boundary для websocket~~ — **RESOLVED**: v1 использует bootstrap-issued short-lived session token
- какие команды доступны только в full
- ~~нужен ли отдельный /api/v1/ha/state snapshot endpoint для fast reconnect~~ — **RESOLVED**: добавлен `/api/v1/ha/state` endpoint
- будет ли catalog_changed содержать diff или только требование полного refetch

Non-protocol questions moved to `ha-04-hacs-integration-plan.md`:
- как именно хранить local dashboard overrides в HA
- будет ли dashboard идти как custom Lovelace cards или как panel

---

## 4.6 State Snapshot (for fast reconnect)

```
GET /api/v1/ha/state
```

**Назначение:**

- fast reconnect recovery
- authoritative full state snapshot

**Пример ответа:**

```json
{
  "projection_epoch": "2026.03.14-001",
  "sequence": 142,
  "entities": {
    "system.connection": {
      "state": true,
      "attributes": {}
    }
  },
  "collections": {
    "assets.snapshot": {...},
    "portfolio.snapshot": {...}
  }
}
```

---

## 20. Рекомендуемая реализация структуры со стороны IRIS

Примерно так:

```
backend/src/apps/integrations/ha/
  api/
  bridge/
  services.py
  query_services.py
  repositories.py
  schemas.py
  websocket.py
  catalog.py
  dashboard.py
  command_bus.py
```

---

## 21. Рекомендуемая структура HA integration

```
custom_components/iris/
  __init__.py
  manifest.json
  config_flow.py
  const.py
  client.py
  websocket_client.py
  catalog.py
  entity_factory.py
  store.py
  sensor.py
  binary_sensor.py
  button.py
  switch.py
  select.py
  event.py
  dashboard.py
  services.yaml
```

---

## 22. Итоговая формулировка

IRIS ↔ HA интеграция строится как server-driven, event-driven, bidirectional protocol, где:

- IRIS публикует catalog, commands, dashboard schema и runtime events
- HA materialize-ит только допустимые entities и хранит collections в runtime store
- команды выполняются через websocket command bus
- entity и UI эволюционируют декларативно, без ручной дубликации логики между IRIS и Home Assistant
