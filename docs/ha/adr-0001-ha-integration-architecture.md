# IRIS ↔ Home Assistant Integration Architecture

> **Status: Non-normative overview**
> 
> Этот документ — архитектурная записка (ADR-like). Детальные спецификации см. в:
> - `ha-02-protocol-spec.md` — протокол (authoritative)
> - `ha-03-backend-plan.md` — реализация backend
> - `ha-04-hacs-integration-plan.md` — реализация HA интеграции
> 
> В случае расхождений между этим документом и spec — **spec является источником истины**.

## Цель

Обеспечить двустороннюю интеграцию IRIS с Home Assistant, при которой:

- IRIS остаётся источником истины для сущностей, команд и UI-моделей.
- Home Assistant выступает как UI-хост, automation engine и notification layer.
- синхронизация выполняется через event bus и server-driven catalog, без polling.
- интеграция поддерживает динамические сущности и расширяемость IRIS без изменения HA-компонента.

---

## Общая архитектура

Система состоит из двух компонентов.

```
┌─────────────────────────────────────────────────────────────────┐
│                           IRIS Backend                          │
│  ┌───────────────┐                                              │
│  │   Event Bus   │  (Redis Streams)                             │
│  │  (Redis)      │                                              │
│  └───────┬───────┘                                              │
│          │                                                       │
│  ┌───────▼────────┐                                             │
│  │  HA Event      │                                              │
│  │  Consumer      │ ──►  WebSocket / Event Gateway              │
│  └────────────────┘                                             │
│                                                                 │
│  ┌───────────────────────────────────────┐                      │
│  │     HA Entity Catalog API             │                      │
│  └───────────────────────────────────────┘                      │
│  ┌───────────────────────────────────────┐                      │
│  │     HA Command API                    │                      │
│  └───────────────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Home Assistant                             │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │     Custom Integration: iris                              │  │
│  │                                                           │  │
│  │   ┌─────────────┐   ┌─────────────────┐   ┌───────────┐ │  │
│  │   │   WebSocket │   │      Entity     │   │  Command  │ │  │
│  │   │   client    │   │   materializer  │   │   bridge  │ │  │
│  │   └─────────────┘   └─────────────────┘   └───────────┘ │  │
│  │                                                           │  │
│  │   ┌─────────────────┐   ┌──────────────────────────────┐  │  │
│  │   │ Runtime state   │   │     Dashboard renderer      │  │  │
│  │   │     store       │   │                              │  │  │
│  │   └─────────────────┘   └──────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Компонент 1: IRIS HA Bridge (backend)

### Назначение

IRIS HA Bridge отвечает за:

- трансляцию событий из IRIS event bus → Home Assistant
- предоставление каталога сущностей
- обработку команд из HA
- передачу runtime state

Этот компонент будет встроен в backend IRIS.

### 1.1 Event Bus Consumer

В системе уже существует consumer Home Assistant в event bus.

**Сейчас он:**

```
event -> print()
```

**Необходимо расширить его до HA Bridge Service.**

#### Новый функционал

Consumer должен:

1. слушать события Redis Streams `iris_events`
2. фильтровать события для HA
3. публиковать их через WebSocket Gateway

#### Типы событий

IRIS должен транслировать:

- decision_generated
- final_signal_generated
- market_regime_changed
- prediction_confirmed
- prediction_failed
- portfolio_action
- portfolio_state_changed
- pattern_state_changed
- operation_started
- operation_progress
- operation_completed
- operation_failed

Каждое событие должно иметь стандартный envelope.

#### Event envelope

```json
{
  "event_type": "decision_generated",
  "timestamp": "...",
  "source": "decision_engine",
  "payload": {...}
}
```

### 1.2 WebSocket Gateway

HA integration будет подключаться к IRIS через WebSocket.

**Причины:**

- двусторонняя связь
- push-обновления
- command execution
- operation tracking

**Endpoint:** `/api/v1/ha/ws`

#### Поддерживаемые сообщения

**Server → HA**

- state_patch
- entity_state_changed
- collection_patch
- catalog_changed
- dashboard_changed
- operation_update
- system_health

**HA → Server**

- command_execute
- subscribe
- unsubscribe
- ack_event
- ping

---

## Компонент 2: Home Assistant Custom Integration

`custom_components/iris`

Этот компонент является тонким адаптером между IRIS и HA.

### 2.1 Основные задачи

Интеграция должна:

1. обнаруживать IRIS через mDNS / zeroconf
2. устанавливать WebSocket соединение
3. запрашивать entity catalog
4. материализовывать HA entities
5. поддерживать runtime state store
6. принимать события и обновлять entities
7. отправлять команды IRIS
8. создавать dashboard

### 2.2 Discovery

IRIS должен публиковать zeroconf:

```
_iris._tcp.local
```

**TXT records:**

- instance_id
- version
- api_port
- ws_path
- mode

HA integration:

```yaml
# manifest.json
zeroconf:
  - "_iris._tcp.local."
```

### 2.3 Connection Flow

После обнаружения:

1. HA открывает config flow
2. пользователь подтверждает подключение
3. integration получает instance_id
4. открывается websocket
5. integration запрашивает catalog

---

## Каталог сущностей

IRIS должен быть единственной точкой истины для сущностей.

Home Assistant не должен содержать hardcoded entities.

**Endpoint:** `/api/v1/ha/catalog`

**Ответ:**

```json
{
  "catalog_version": "2026.03",
  "mode": "full",
  "entities": [...],
  "collections": [...],
  "commands": [...],
  "views": [...]
}
```

### Entity Definition

Каждая сущность описывается декларативно.

```json
{
  "entity_key": "system.connection",
  "platform": "binary_sensor",
  "name": "IRIS Connection",
  "icon": "mdi:lan-connect",
  "category": "diagnostic",
  "default_enabled": true,
  "state_source": "system.connection",
  "device_class": "connectivity"
}
```

### Поддерживаемые платформы

- sensor
- binary_sensor
- switch
- button
- select
- number
- event

### Materialization Logic

При запуске integration:

1. fetch catalog
2. compare with local registry
3. create new entities
4. update metadata
5. disable deprecated entities

---

## Collection Model

Для больших данных используется collections, а не entity.

**Пример:**

```json
{
  "collection_key": "assets.snapshot",
  "kind": "mapping",
  "transport": "websocket",
  "dashboard_only": true
}
```

**Пример snapshot:**

```json
{
  "assets": {
    "BTC": {
      "decision": "BUY",
      "confidence": 0.81,
      "risk": 0.63
    }
  }
}
```

---

## Command Catalog

IRIS объявляет команды.

**Пример:**

```json
{
  "command_key": "asset.add",
  "input_schema": {
    "symbol": "string"
  },
  "returns": "operation"
}
```

### Поддерживаемые команды

- asset.add
- asset.remove
- asset.watch_enable
- news.connect_source
- news.disconnect_source
- telegram.start_auth
- telegram.confirm_auth
- portfolio.sync
- market.refresh

### Command Execution

HA отправляет:

```json
{
  "type": "command_execute",
  "command": "asset.add",
  "payload": {
    "symbol": "BTC"
  }
}
```

IRIS возвращает: `operation_id`

### Operation Tracking

HA получает события:

- operation_started
- operation_progress
- operation_completed
- operation_failed

---

## Dashboard

IRIS должен предоставлять схему dashboard.

**Endpoint:** `/api/v1/ha/dashboard`

**Ответ:**

```json
{
  "version": 1,
  "views": [...]
}
```

### Dashboard Creation

Integration должна:

1. создать Lovelace dashboard "IRIS"
2. создать views:
   - Overview
   - Assets
   - Signals
   - Portfolio
   - Predictions
   - Integrations
   - System

---

## Entity Strategy

Чтобы избежать тысяч entities:

- **default**: aggregate sensors
- **optional**: user может promote asset → entity

### Lifecycle

Entities могут иметь статус:

- active
- deprecated
- hidden
- removed

### Compatibility

Каждая сущность должна иметь:

- since_version
- deprecated_since
- replacement

---

## Security

Все команды требуют:

- X-IRIS-Actor
- X-IRIS-Access-Mode

---

## Roadmap разработки

### Этап 1

**IRIS:**

- HA bridge service
- event consumer
- websocket gateway

**HA:**

- basic custom integration
- websocket client
- entity materializer

### Этап 2

- entity catalog
- command catalog
- runtime collections

### Этап 3

- dashboard schema
- auto dashboard creation

### Этап 4

- advanced entity lifecycle
- user overrides
- promoted entities

### Этап 5

- Home Assistant addon
- Supervisor integration
- full packaging

---

## Итог

Система должна реализовать server-driven Home Assistant integration, где:

- IRIS является источником истины
- HA является UI и automation layer
- все сущности, команды и dashboard описываются декларативным каталогом
- синхронизация выполняется через event bus и WebSocket
