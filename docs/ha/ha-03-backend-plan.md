# IRIS ↔ Home Assistant
# Backend Implementation Plan

## Цель

Реализовать со стороны IRIS backend-компонент, который:

- принимает внутренние события из event bus
- преобразует их в внешний HA-совместимый поток
- публикует catalog доступных сущностей, collections, commands и dashboard schema
- принимает команды от Home Assistant
- поддерживает двустороннюю websocket-сессию
- остаётся тонким интеграционным слоем поверх доменной логики IRIS, не размывая core-домены

---

## 1. Границы backend-реализации

### В scope

Нужно реализовать:

- HA integration backend module
- websocket gateway
- bridge поверх текущего HA consumer из event bus
- bootstrap/health/catalog/dashboard endpoints
- command dispatch adapter
- runtime state publisher
- catalog versioning
- dashboard schema provider
- operation update relay
- catalog change notifications

### Out of scope для текущего этапа

Пока не делать:

- HA add-on
- автоустановку интеграции
- сложный dashboard editor
- полноценный UI-конструктор внутри control plane
- entity-per-asset promoted mode
- multi-user HA permissions model
- offline queueing для HA

---

## 2. Предлагаемая структура модуля

Рекомендуемая структура в IRIS:

```
backend/src/apps/integrations/ha/
  api/
    router.py
    dependencies.py
    schemas.py
  application/
    services.py
    command_dispatcher.py
    catalog_service.py
    dashboard_service.py
    bootstrap_service.py
  bridge/
    event_consumer.py
    event_mapper.py
    event_publisher.py
    websocket_hub.py
    session_manager.py
    state_projector.py
  domain/
    contracts.py
    enums.py
    models.py
  infrastructure/
    repositories.py
    zeroconf.py
  schemas/
    bootstrap.py
    catalog.py
    dashboard.py
    websocket.py
    commands.py
    events.py
```

### Принцип

- **api/** — HTTP/WebSocket transport
- **application/** — use case orchestration
- **bridge/** — связка event bus → HA external stream
- **schemas/** — отдельные контракты
- **domain/** — минимальные внутренние модели HA bridge
- **infrastructure/** — интеграция с Redis, discovery, storage

---

## 3. Основные backend-компоненты

### 3.1 HA Bridge Module

Новый модуль должен стать единой точкой входа для HA-интеграции со стороны backend.

Он отвечает за:

- экспорт протокола
- экспорт catalog
- экспорт dashboard schema
- прием команд
- публикацию событий наружу

### 3.2 Event Consumer Upgrade

Сейчас consumer Home Assistant уже есть, но только печатает в консоль.

Нужно превратить его в production bridge:

**Было:**

```
event -> print()
```

**Должно стать:**

```
Redis Streams event
  -> HA event mapper
  -> runtime state projector
  -> websocket broadcaster
  -> optional operation relay
```

Новый consumer обязан:

- слушать iris_events
- получать только нужные HA-события
- нормализовать payload
- обновлять внутренний HA runtime state
- рассылать websocket-подписчикам сообщения нужного типа

---

## 4. Event Flow

### 4.1 Входные события из IRIS bus

На первом этапе поддержать минимум:

- decision_generated
- market_regime_changed
- prediction_confirmed
- prediction_failed
- portfolio_action
- portfolio_state_changed
- operation_started
- operation_progress
- operation_completed
- operation_failed

### 4.2 Нормализация событий

Нужен отдельный mapper:

```
bridge/event_mapper.py
```

Он должен:

- принимать внутренний event envelope
- преобразовывать его в HA external protocol message
- гарантировать единый формат вне зависимости от внутреннего домена

### 4.3 Выходные типы websocket-сообщений

Bridge должен уметь публиковать:

- event_emitted
- entity_state_changed
- state_patch
- collection_patch
- collection_snapshot
- operation_update
- catalog_changed
- dashboard_changed
- system_health

---

## 5. Runtime State Projection

### Задача

Нужен слой, который будет собирать "представление для HA" из внутренних событий IRIS.

Это не должен быть прямой passthrough сырых событий.

Для этого нужен `state_projector.py`

Он должен:

- вести in-memory runtime state для HA
- знать пути вида:
  - system.connection
  - portfolio.summary.available_capital
  - market.summary.hot_assets_count
  - integrations.telegram.auth_status
- обновлять collections:
  - assets.snapshot
  - portfolio.snapshot
  - predictions.snapshot
  - integrations.snapshot

### Важно

Projector не должен становиться вторым domain layer.
Он только строит external projection model.

---

## 6. Entity Catalog

### Цель

IRIS должен стать единственной точкой истины для списка сущностей, которые HA может materialize.

Реализовать `catalog_service.py`

Этот сервис должен:

- собирать entity catalog декларативно
- учитывать режим запуска:
  - full
  - local
  - позже ha_addon
- учитывать включенные фичи
- возвращать:
  - entities
  - collections
  - commands
  - views

### Каталог должен быть backend-owned

То есть список сущностей должен формироваться в IRIS, а не быть захардкожен в HA integration.

### 6.1 Что должно входить в v1 catalog

**entities**

Минимально:

- system connection
- system mode
- active assets count
- hot assets count
- portfolio value
- open positions
- notifications enabled
- market summary status
- integration health

**collections**

Минимально:

- assets.snapshot
- portfolio.snapshot
- predictions.snapshot
- integrations.snapshot

**commands**

Минимально:

- asset.add
- asset.remove
- portfolio.sync
- market.refresh
- telegram.start_auth
- telegram.confirm_auth
- news.connect_source
- news.disconnect_source

**views**

Минимально:

- overview
- assets
- portfolio
- integrations
- system

### 6.2 Catalog versioning

Нужен механизм версионирования каталога.

Минимум:

- catalog_version строкой
- изменение при любом изменении состава entity/commands/views/collections
- websocket event catalog_changed

---

## 7. Dashboard Schema

Реализовать `dashboard_service.py`

Он должен отдавать server-driven dashboard schema.

Пока достаточно v1 dashboard contract:

- slug
- title
- views
- sections
- widgets
- data bindings

### Не надо в v1

- визуальный редактор
- двустороннее редактирование layout
- сложные пользовательские макеты

---

## 8. Bootstrap и Health

Реализовать HTTP endpoints

### /api/v1/ha/health

Должен возвращать:

- статус
- instance_id
- version
- protocol_version
- catalog_version
- mode
- websocket_supported

### /api/v1/ha/bootstrap

Должен возвращать:

- instance metadata
- capability flags
- catalog URL
- dashboard URL
- ws URL

---

## 9. WebSocket Gateway

Реализовать endpoint:

```
/api/v1/ha/ws
```

### Компоненты

**websocket_hub.py**

Отвечает за:

- broadcast
- topic subscriptions
- routing session messages

**session_manager.py**

Отвечает за:

- handshake
- client registry
- connection lifecycle
- cleanup on disconnect

### 9.1 Поддерживаемые клиентские сообщения

Нужно реализовать обработку:

- hello
- subscribe
- unsubscribe
- command_execute
- ping

### 9.2 Поддерживаемые серверные сообщения

Нужно реализовать:

- welcome
- pong
- entity_state_changed
- state_patch
- collection_snapshot
- collection_patch
- operation_update
- catalog_changed
- dashboard_changed
- event_emitted
- **command_ack**

---

## 9.x Failure Semantics and Backpressure

### Per-session outbound queue

- Maximum queue depth per session: 1000 messages
- If queue overflows: send `resync_required` to client, close connection gracefully
- Coalescing: duplicate state_patch for same entity within 100ms window → send only latest

### Slow consumer handling

- Monitor client read rate
- If client is too slow: disconnect with `slow_consumer` reason

### Resynchronization rules

- Backend restart: increment `projection_epoch`, reset `sequence` to 0
- On reconnect: client MUST fetch `/api/v1/ha/state` or do full resync
- If client detects sequence gap: trigger full resync

### Process restart

- In-memory projector state does NOT survive restart
- Clients MUST reconnect and resync
- No persistent state in v1

---

## 10. Command Dispatch

### Цель

Home Assistant должен иметь возможность вызывать команды, но backend не должен превращаться в мешанину из хаотичных if/else.

Реализовать `command_dispatcher.py`

Он должен:

- принимать command key
- валидировать payload по schema
- проверять доступность команды в текущем mode
- прокидывать команду в соответствующий application service
- возвращать:
  - immediate ack
  - operation_id, если команда асинхронная

### 10.1 Command routing strategy

Вместо ручного свитча лучше сделать registry:

```
command_key -> handler
```

Например:

- asset.add -> asset application service
- portfolio.sync -> portfolio orchestration service
- telegram.start_auth -> integrations service

### 10.2 Operation integration

Если команда запускает долгую операцию:

- backend сразу возвращает command_ack
- далее operation lifecycle идет через websocket operation_update

---

## 11. Связь с Control Plane

Ты уже правильно отметил, что каталог включаемых/выключаемых сущностей хорошо ложится на control-plane.

### На текущем этапе

Нужно использовать control-plane как управляющую плоскость доступности HA projections, но не перегружать её.

### Что можно отдать в control-plane уже сейчас

- включена ли entity по умолчанию
- включена ли collection
- доступна ли команда
- доступен ли view/widget

### Что пока не надо

- полноценный drag-and-drop editor HA dashboard
- отдельную orchestration graph для HA UI

### Практический вариант v1

Сделать HA catalog configurable через control-plane-backed config storage:

```
ha_entities
ha_collections
ha_commands
ha_views
```

То есть control-plane задает policy, а catalog_service строит конечный результат.

### Policy Precedence Model

Порядок приоритетов (от высшего к низшему):

1. **Domain constraints** — hard limits (e.g., entity not allowed in current mode)
2. **Mode constraints** — full/local/ha_addon restrictions
3. **Feature flags** — какие фичи включены
4. **Control-plane policy** — user-defined overrides from CP
5. **Backend defaults** — values from catalog
6. **HA local overrides** — user settings in HA (name, area, disabled)

---

### Observability

**Required metrics:**

- `ha_ws_active_sessions` — gauge
- `ha_ws_outbound_queue_depth` — gauge
- `ha_projection_apply_failures_total` — counter
- `ha_projection_lag_ms` — histogram
- `ha_catalog_refetch_total` — counter
- `ha_command_ack_latency_ms` — histogram
- `ha_operation_update_latency_ms` — histogram

---

## 12. Auth / Security

### v1 Решение

**WebSocket Auth:** bootstrap-issued short-lived session token

- bootstrap endpoint возвращает `session_token` в ответе
- client передаёт токен при WebSocket handshake (через query param или header)
- токен имеет ограниченное время жизни

**HTTP Headers:**

- X-IRIS-Actor
- X-IRIS-Access-Mode

### Dev/Local Profile

Для локальной разработки: trusted local mode (без токена).

### Важно

Код должен поддерживать расширение auth схемы в будущем.

---

## 13. Состояние и хранение

### Что нужно хранить в памяти

Допустимо хранить:

- websocket sessions
- current runtime state projection
- last collection snapshot
- last known catalog version

### Что лучше не класть в постоянное хранение на этом этапе

Пока не нужно отдельно персистить:

- HA runtime store
- dashboard user layout
- session history

Это можно добавить позже, если действительно понадобится fast reconnect state snapshot с диска/redis.

---

## 14. Error Handling

Нужно сразу сделать единый error contract.

Для HTTP и websocket ошибок

Должен быть общий формат:

```json
{
  "error": {
    "code": "command_not_available",
    "message": "Command is not available in current mode",
    "details": {}
  }
}
```

### Минимальные error codes

- invalid_message
- unsupported_protocol_version
- unauthorized
- forbidden
- command_not_available
- invalid_payload
- catalog_outdated
- internal_error

---

## 15. Тестирование

### Обязательно покрыть

**unit tests**

- event mapping
- catalog generation
- dashboard schema generation
- command dispatcher routing
- state projector updates

**integration tests**

- websocket hello/welcome flow
- subscribe/unsubscribe
- command execution ack
- operation update propagation
- catalog_changed delivery
- collection snapshot/patch flow

**event bus tests**

- consumer читает событие
- mapper нормализует
- projector обновляет state
- hub рассылает websocket message

---

## 16. Поэтапный roadmap backend-разработки

### Этап 1 — skeleton

Сделать каркас модуля:

- структура пакета
- router
- health
- bootstrap
- websocket endpoint skeleton

### Этап 2 — event bridge

Доработать текущий HA consumer:

- event mapper
- state projector
- websocket broadcast

### Этап 3 — catalog

Сделать:

- entity catalog
- collection catalog
- command catalog
- catalog versioning

### Этап 4 — command bus

Сделать:

- command dispatcher
- handler registry
- operation ack/update integration

### Этап 5 — dashboard schema

Сделать:

- dashboard service
- базовые views/sections/widgets
- dashboard_changed

### Этап 6 — control-plane binding

Сделать:

- configurable enable/disable entities
- configurable commands/views
- control-plane-backed policy layer

### Этап 7 — hardening

Сделать:

- auth boundary
- reconnect behavior
- richer health/system status
- error normalization
- protocol compatibility checks

---

## 17. Definition of Done

Backend-часть считается готовой, когда:

- [ ] есть рабочий /api/v1/ha/health
- [ ] есть рабочий /api/v1/ha/bootstrap
- [ ] есть рабочий /api/v1/ha/catalog
- [ ] есть рабочий /api/v1/ha/dashboard
- [ ] есть рабочий /api/v1/ha/state (для fast reconnect)
- [ ] websocket handshake работает
- [ ] event consumer публикует HA-compatible сообщения
- [ ] catalog собирается из backend и не дублируется в HA
- [ ] команды можно вызывать из HA через websocket
- [ ] долгие команды отдают operation_id
- [ ] есть catalog_changed
- [ ] entity availability можно включать/выключать через backend policy
- [ ] покрыты unit и integration тесты
- [ ] **клиент переживает reconnect без ручного вмешательства и с корректным resync**
- [ ] **command rejection идёт через единый command_ack/error формат**
- [ ] **есть метрики/диагностика для session lifecycle и projector lag**

---

## 18. Самые тонкие места, которые нельзя запороть

1. **Не смешать HA bridge с core domain logic**
   Никакой доменной аналитики внутрь apps/integrations/ha тащить нельзя.

2. **Не превратить collections в giant sensor transport**
   Collections должны оставаться отдельной моделью данных.

3. **Не делать hardcoded entity list в двух местах**
   Каталог только backend-owned.

4. **Не завязать websocket protocol на внутренние event names слишком жестко**
   Нужен mapper, а не прямой passthrough.

5. **Не удалять сущности агрессивно**
   Только lifecycle-driven подход.

---

## 19. Короткое итоговое решение

На backend IRIS нужно разработать HA Bridge module, который:

- читает события из IRIS event bus
- строит HA-oriented runtime projection
- отдает server-driven catalog
- принимает команды из HA
- транслирует всё через websocket protocol
- использует control-plane как policy source для доступности entity/commands/views
