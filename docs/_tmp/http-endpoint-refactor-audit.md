# IRIS HTTP Endpoint Refactor Audit And Standard

## Цель

Жестко привести HTTP surface проекта к единому стандарту, как это уже было сделано для persistence-layer.

Нужен не косметический проход по `views.py`, а прямой cutover:

- убрать transport-логику, которая разрослась внутри endpoint-модулей;
- разнести read / write / jobs / webhooks / streaming по отдельным HTTP adapters;
- унифицировать route prefix, error mapping, response contracts и operation endpoints;
- ввести единый versioned API root: `/api/v1`;
- перейти на `async-func-first` endpoint style;
- не сохранять старые внутренние endpoint-helper patterns, если они мешают целевой структуре;
- не держать giant `views.py` как второй application layer.

## Прогресс cutover

Уже переведено на новый HTTP standard:

- корневой router tree: `backend/src/api/router.py` -> `backend/src/api/v1/router.py`
- shared transport foundation: `backend/src/core/http/*`
- `backend/src/apps/control_plane/api/*`
- `backend/src/apps/market_structure/api/*`
- `backend/src/apps/news/api/*`
- `backend/src/apps/signals/api/*`
- `backend/src/apps/market_data/api/*`
- `backend/src/apps/hypothesis_engine/api/*`
- `backend/src/apps/patterns/api/*`
- `backend/src/apps/indicators/api/*`
- `backend/src/apps/portfolio/api/*`
- `backend/src/apps/predictions/api/*`
- `backend/src/apps/system/api/*`

Удалено:

- `backend/src/apps/control_plane/views.py`
- `backend/src/apps/market_structure/views.py`
- `backend/src/apps/news/views.py`
- `backend/src/apps/signals/views.py`
- `backend/src/apps/market_data/views.py`
- `backend/src/apps/hypothesis_engine/views.py`
- `backend/src/apps/patterns/views.py`
- `backend/src/apps/indicators/views.py`
- `backend/src/apps/portfolio/views.py`
- `backend/src/apps/predictions/views.py`
- `backend/src/apps/system/views.py`

## Текущая HTTP поверхность

Endpoint modules:

- `backend/src/apps/system/api/router.py` + split endpoint modules
- `backend/src/apps/market_data/api/router.py` + split endpoint modules
- `backend/src/apps/news/api/router.py` + split endpoint modules
- `backend/src/apps/hypothesis_engine/api/router.py` + split endpoint modules
- `backend/src/apps/patterns/api/router.py` + split endpoint modules
- `backend/src/apps/signals/api/router.py` + split endpoint modules
- `backend/src/apps/indicators/api/router.py` + split endpoint modules
- `backend/src/apps/portfolio/api/router.py` + split endpoint modules
- `backend/src/apps/predictions/api/router.py` + split endpoint modules
- `backend/src/apps/market_structure/api/router.py` + split endpoint modules
- `backend/src/apps/control_plane/api/router.py` + split endpoint modules

Bootstrap wiring:

- `backend/src/core/bootstrap/app.py` подключает только корневой `api` router
- `backend/src/api/v1/router.py` централизованно монтирует versioned surface `/api/v1`
- все активные домены уже подключаются через domain-local `build_router(mode, profile)`
- active runtime HTTP surface больше не использует legacy `views.py` modules

Первый structural gap уже закрыт:

- в проекте есть явный корневой API router `/api`, под которым живет `/v1`, и уже под `/v1` подключаются доменные routers

## Главные проблемы

### 1. Нет единого router structure standard

Сейчас endpoint-слой собран разнородно:

- где-то используется `APIRouter(prefix=...)`, где-то prefix размазан по каждому decorator path;
- где-то один модуль содержит только read endpoints, где-то он одновременно держит reads, writes, jobs, onboarding, webhook ingestion и auth headers;
- naming и route ownership не унифицированы.

Следствие:

- трудно делать массовый рефактор URL surface;
- трудно выносить общие transport rules;
- тяжело ревьюить и тестировать modules как bounded HTTP adapters.

### 2. `views.py` во многих доменах стали transport-god modules

Самые тяжелые примеры:

- `backend/src/apps/indicators/views.py`
- `backend/src/apps/portfolio/views.py`
- `backend/src/apps/system/views.py`

Типичные симптомы:

- много endpoint categories в одном файле;
- ручная сериализация / mapping;
- ручной exception translation;
- inline job dispatch;
- inline header parsing / token handling;
- inline SSE/webhook orchestration.

### 3. Transport mapping течет в view layer

Самые явные примеры:

- `backend/src/apps/control_plane/views.py`: много `_..._read(...)` helper-ов для преобразования query/read models в response DTO
- `backend/src/apps/market_structure/views.py`: `_snapshot_schema_from_read_model`
- `backend/src/apps/system/views.py`: `_source_status_rows()` строит operational payload прямо в endpoint module
- `backend/src/apps/indicators/views.py`: transport composition смешана с cross-domain read orchestration

Это означает:

- HTTP adapter знает слишком много о внутреннем shape данных;
- serialization policy не централизована;
- endpoint file превращается в смесь transport + presentation + orchestration.

### 4. Повторяющийся command-endpoint boilerplate

Почти везде повторяется один и тот же паттерн:

1. проверить существование через query service;
2. вызвать application service;
3. вручную отловить domain exception;
4. вручную превратить его в `HTTPException`;
5. вручную сделать `await uow.commit()`;
6. вернуть response DTO.

Это видно в:

- `backend/src/apps/indicators/views.py`
- `backend/src/apps/portfolio/views.py`
- `backend/src/apps/system/views.py`

Нужен единый command-endpoint standard, иначе у нас десятки почти одинаковых endpoint handlers.

### 5. Job / admin / onboarding / webhook endpoints смешаны с public read surface

Сейчас в одних и тех же файлах живут:

- public query endpoints;
- admin mutation endpoints;
- background job trigger endpoints;
- onboarding flows;
- ingest/webhook endpoints;
- control/auth-only endpoints.

Самые проблемные домены:

- `indicators`
- `portfolio`
- `system`

Это надо разделить. Иначе у нас нет нормальной границы между:

- public read API
- command API
- operational API
- ingest/webhook API
- stream API

### 6. Inconsistent response contracts

Сейчас response shape неоднороден:

- где-то возвращаются строго typed read models;
- где-то `dict[str, object]` queue responses;
- где-то fallback через `ValidationError` и "вернуть как получилось";
- где-то HTTP 202 queue endpoints возвращают ad-hoc payload;
- pagination envelope практически отсутствует, почти везде просто `list[...]`.

Это особенно видно в:

- `backend/src/apps/indicators/views.py`
- `backend/src/apps/portfolio/views.py`
- `backend/src/apps/system/views.py`

### 7. Error handling policy не централизована

Почти каждый модуль вручную маппит domain exceptions в `HTTPException`.

Сейчас это размазано по множеству handler-ов:

- `news`
- `market_structure`
- `control_plane`
- `indicators`
- `portfolio`
- `system`

Нужен единый способ:

- либо domain-specific `api/errors.py`
- либо shared exception-to-http translator
- либо explicit presenter/adapter layer per app

### 8. Некоторые endpoint modules держат не только HTTP adapter, но и runtime mechanics

Самые заметные случаи:

- `backend/src/apps/system/views.py`: source/rate-limit operational state assembly
- `backend/src/apps/market_structure/views.py`: ingest token extraction и native webhook orchestration
- `backend/src/apps/indicators/views.py`: cross-domain composition and analytics projection ownership

Это нужно выносить в отдельные transport helpers или dedicated API submodules.

### 9. URL ownership и ресурсная модель читаются не всегда ясно

Сейчас много paths hanging off `/coins/{symbol}/...` из разных доменов:

- `market_data`
- `patterns`
- `signals`

Это допустимо, но без общего HTTP standard становится неясно:

- где canonical coin resource;
- где projections;
- где analytics subresources;
- где operational commands.

Плюс path styles смешаны:

- `/news/sources/{id}/jobs/run`
- `/market-structure/health/jobs/run`
- `/hypothesis/jobs/evaluate`
- `/control-plane/drafts/{id}/apply`

Нужна строгая policy по command endpoints и operation resources.

## Целевой HTTP стандарт

### 0. Общая иерархия маршрутизации

Целевой routing tree:

```text
/api
  /v1
    /system
    /market-data
    /news
    /market-structure
    /indicators
    /patterns
    /signals
    /portfolio
    /predictions
    /hypothesis
    /control-plane
```

Центральная структура:

```text
src/api/router.py
src/api/v1/router.py
```

Правила:

- `create_app()` подключает только корневой API router;
- `src/api/router.py` подключает только version routers;
- `src/api/v1/router.py` подключает только доменные routers;
- доменные endpoint modules не должны знать про `/api` и `/v1`;
- прямо сейчас вводим только `/api/v1`;
- `v2`, `v3` и т.д. не создаются заранее без реальной versioning policy.

### 1. Обязательный shared HTTP core

Новый standard нельзя строить только на per-domain `api/` packages. Нужен общий transport foundation:

```text
src/core/http/
  __init__.py
  contracts.py
  errors.py
  pagination.py
  responses.py
  presenters.py
  command_executor.py
  router_policy.py
  launch_modes.py
  operations.py
  tracing.py
```

Обязанности shared core:

- `contracts.py`: общие transport DTO и базовые `Pydantic` схемы, например `PageRequest`, `CursorPageRequest`, `PageEnvelope[T]`, `AcceptedResponse`, `CreatedResponse[T]`, `OperationResponse`, `OperationStatusResponse`;
- `errors.py`: единый `ApiError` contract, error body factory, shared domain-to-http translation hooks;
- `pagination.py`: default limits, max limits, cursor/page policy, sort naming;
- `responses.py`: typed helpers для `201/202/204/page/list/stream`;
- `presenters.py`: базовые presenter protocols и общие composition helpers;
- `command_executor.py`: единый command execution flow с commit, error mapping и success response shaping;
- `router_policy.py`: tags, prefix, include order, version mounting conventions;
- `launch_modes.py`: `full`, `local`, `ha_addon` и общие правила mode-aware router assembly;
- `operations.py`: operation statuses, result references, retry metadata, deduplication metadata;
- `tracing.py`: `request_id`, `correlation_id`, `causation_id` и их transport-level propagation rules.

### 2. Один `api/` package на домен и один публичный router entrypoint

Для каждого app:

```text
src/apps/<domain>/api/
  __init__.py
  router.py
  deps.py
  errors.py
  presenters.py
  contracts.py
  read_endpoints.py
  command_endpoints.py
  job_endpoints.py
  webhook_endpoints.py        # только если реально есть
  stream_endpoints.py         # только если реально есть
```

Правила:

- `views.py` как giant entrypoint нужно удалить по мере миграции;
- домен экспортирует только один публичный HTTP entrypoint: `src/apps/<domain>/api/router.py`;
- `bootstrap/app.py` не должен знать о внутренних `read_endpoints.py`, `job_endpoints.py`, `stream_endpoints.py`;
- `router.py` внутри домена агрегирует subrouter-ы и является единственной публичной точкой подключения домена;
- рекомендуемый контракт: `build_router(mode: LaunchMode, profile: DeploymentProfile) -> APIRouter`.

### 3. Endpoint files должны быть async-func-first и содержать только handlers

Endpoint module это файл с реальными async endpoint handlers, а не с half-framework logic.

В endpoint module допускается только:

- `router = APIRouter(...)`
- `@router.get/post/patch/put/delete(...)`
- `async def ...(...)`
- request/path/query parsing через типизированные transport arguments
- вызов dependency-provided use-case interface
- возврат `Pydantic` response schema
- перевод domain/app errors в HTTP errors

В endpoint module запрещено держать:

- dependency builders;
- service assembly;
- presenter/serializer helpers;
- private `_read/_payload/_response` builders;
- auth/header parsing policy helpers;
- SSE/webhook/runtime support utilities;
- Redis/queue/bootstrap orchestration helpers;
- stream consumer lifecycle logic;
- fallback serialization behavior.

Все это выносится в:

- `deps.py`
- `errors.py`
- `presenters.py`
- `contracts.py`
- dedicated stream/webhook adapters

### 4. Transport contracts только через Pydantic schemas

Для request/response слоя используются только `Pydantic` схемы.

Правила:

- request body контракты описываются `BaseModel` схемами;
- response контракты описываются `BaseModel` схемами;
- `response_model` обязателен для всех публичных endpoints, кроме осознанных `204` ответов;
- handlers не возвращают dataclass, ORM model, `dict[str, Any]` или mixed payload как публичный transport contract;
- presenter обязан маппить read model или result object в `Pydantic` response schema;
- validation не должна быть размазана по helper dependencies: `Depends(...)` не используется для transport-validation моделей, он используется для runtime dependencies;
- если endpoint принимает query filters, они должны быть оформлены как явный typed transport contract, а не как россыпь невалидированных строк.

### 5. Dependency Injection Policy для endpoint layer

Через dependency endpoint должен получать уже собранный application-facing interface.

Правильно:

- read endpoint получает `QueryService` или dedicated read facade;
- command endpoint получает command service;
- job endpoint получает operation/job service;
- webhook endpoint получает ingest service;
- stream endpoint получает stream adapter/service;
- при необходимости endpoint получает auth/access dependency или presenter dependency.

Неправильно:

- передавать в endpoint `AsyncSession`;
- передавать `Repository`;
- передавать и session, и repo, и query service россыпью;
- передавать raw Redis client;
- передавать raw queue client или raw TaskIQ dispatch imports;
- собирать service внутри handler-а вручную;
- передавать один giant service на весь домен, если у него несвязанные сценарии;
- использовать `Depends(...)` для transport validation helper-ов, если через `Depends` в handler фактически должен приходить только runtime service/facade.

Правило сборки:

- dependency wiring лежит только в `deps.py`;
- там же собираются `uow`, `repositories`, `query services`, `loggers`, auth/access context и прочие infra pieces;
- endpoint ничего не знает о том, как объект был собран;
- если у endpoint есть `Depends(...)`, то это должен быть уже готовый service/facade или стандартизованная access dependency, а не низкоуровневая infra деталь.

### 6. Router assembly contract и mode-aware mounting

Сборка router tree должна быть детерминированной.

Правила:

- `bootstrap/app.py` подключает только root API router;
- `src/api/v1/router.py` подключает только domain root routers;
- доменный `router.py` сам агрегирует `read_endpoints`, `command_endpoints`, `job_endpoints`, `webhook_endpoints`, `stream_endpoints`;
- mode gating не размазывается по handler-ам;
- рекомендуемый подход: `build_router(mode: LaunchMode, profile: DeploymentProfile) -> APIRouter`, где домен сам знает свои категории surface, а bootstrap централизованно передает mode/profile.

### 7. HTTP adapter responsibility contract

HTTP adapter может делать только:

- parse request DTO;
- resolve dependencies;
- вызвать query service / application service / facade;
- завершить command transaction boundary через стандартизованный helper;
- преобразовать результат через presenter;
- выполнить HTTP-level error mapping;
- вернуть typed response contract.

HTTP adapter не должен делать:

- прямой доступ к repository;
- SQL/ORM orchestration;
- Redis stream iteration logic;
- queue dispatch mechanics в raw виде;
- сложную domain data composition;
- header parsing policy как transport-local improvisation;
- cross-domain orchestration без явной facade boundary;
- ручную сборку больших operational payload-ов;
- domain snapshot reconstruction;
- ingestion token extraction внутри handler-а;
- stream consumer lifecycle management.

### 8. Разделять surfaces по ответственности

Минимально:

- `read_endpoints.py`: GET/read-only;
- `command_endpoints.py`: POST/PATCH/PUT/DELETE mutations;
- `job_endpoints.py`: queue/trigger/run operations;
- `webhook_endpoints.py`: external ingest;
- `stream_endpoints.py`: SSE/streaming.

Дополнительно при необходимости:

- `onboarding_endpoints.py`;
- `admin_endpoints.py`;
- `observability_endpoints.py`.

### 9. Command endpoint standard

Повторяющийся шаблон command endpoint должен быть стандартизован через общий helper.

Базовый flow:

1. request DTO parsing;
2. dependency resolution;
3. optional auth/access enforcement;
4. application service call;
5. `await uow.commit()` через общий command executor;
6. presenter -> response DTO;
7. standardized success response.

Обязательное правило:

- для HTTP command endpoints commit должен быть transport-controlled через единый `core/http/command_executor.py`;
- смешанный стиль, где часть endpoint-ов коммитит сама, часть через helper, часть через сервис, недопустим.

### 10. Единый response contract standard

Command response standard:

- `201 Created`: только когда создан новый canonical resource и есть его `Pydantic` response schema;
- `202 Accepted`: только для queued/job/run/async trigger endpoints и только через единый typed `AcceptedResponse`;
- `204 No Content`: только для delete/discard/toggle-like operations без response body;
- `200 OK`: для synchronous mutation result, если нужен updated resource representation или explicit operation payload.

List response standard:

- для потенциально больших коллекций нельзя возвращать голый `list[...]`;
- нужен envelope с `items`, page/cursor metadata, applied filters, optional sort metadata;
- для маленьких справочников допустим прямой список только как явное исключение.

### 11. Pagination / filter / sort governance

Нужно централизованно зафиксировать:

- default limit;
- max limit;
- cursor policy для больших коллекций;
- page/size policy только для ограниченных admin/reference списков;
- filter naming;
- sort naming.

Обязательные naming rules:

- одинаковые поля называются одинаково во всех доменах: `symbol`, `timeframe`, `source_id`, `status`, `created_after`, `created_before`;
- sort naming единообразно: `sort_by`, `sort_order`;
- нельзя смешивать `from_ts` / `start` / `since` для одной и той же семантики.

### 12. Resource / projection / operation / job / webhook / stream policy

Каждый endpoint должен быть классифицирован как один из surface types:

- resource endpoint: canonical domain object;
- projection endpoint: derived read-only view;
- operation endpoint: non-CRUD action;
- job endpoint: async operational trigger;
- webhook/ingest endpoint: внешний ingest surface;
- stream endpoint: SSE/streaming surface.

Правила:

- operation endpoints не маскируются под CRUD;
- job endpoints должны выглядеть как operational surface;
- webhook endpoints не должны выглядеть как внутренние admin commands;
- stream endpoints живут отдельно от read/command paths;
- URL semantics должны быть читаемыми и предсказуемыми.

### 13. Stream endpoint standard

Streaming это отдельный transport category, а не обычный endpoint.

Stream endpoint должен делать только:

- auth/access resolution;
- subscribe request parsing;
- вызов stream adapter/service;
- packaging response as SSE/streaming response.

Stream endpoint не должен делать:

- Redis group creation logic;
- consumer lifecycle orchestration;
- low-level retry loops;
- broker-specific event assembly;
- stream event polling mechanics.

Должен быть отдельный stream adapter layer, например:

- `src/apps/<domain>/api/stream_adapter.py`
- или `src/apps/<domain>/transport/streaming.py`

### 14. Error mapping standard

Нужен shared base translator + domain-local extension.

Стандарт:

- `src/core/http/errors.py` задает общий error framework и `ApiError` response shape;
- `src/apps/<domain>/api/errors.py` расширяет mapping для своих exception types;
- repeated `try/except -> HTTPException` в handler-ах не допускается, если mapping повторяется;
- policy для `400`, `401`, `403`, `404`, `409`, `422` должна быть единообразной;
- поведение `202/409` для already-running jobs должно быть стандартизовано.

### 15. OpenAPI governance

OpenAPI является частью Definition of Done.

Нужно стандартизовать:

- tags;
- operationId;
- response docs;
- schema naming;
- explicit known error responses;
- security requirements;
- pagination schemas;
- typed accepted/queued responses.

Правила:

- response models называются предсказуемо: `NewsSourceResponse`, `NewsSourcePageResponse`, `AcceptedJobResponse`, `DraftApplyResponse`;
- теги должны отражать домен и surface category, например `news:read`, `news:commands`, `market-structure:webhooks`, `hypothesis:streams`;
- `operationId` должен следовать одному convention, например `news_list_sources`, `control_plane_apply_draft`.

### 16. Launch modes как архитектурное ограничение HTTP surface

HTTP surface должен быть mode-aware.

Поддерживаемые режимы:

- `full`;
- `local`;
- `ha_addon`.

Ключевые правила:

- launch mode влияет на доступные routers, operational endpoints, onboarding, webhooks, streams и auth/access policy;
- `local` не создает отдельный хаотичный API, это тот же router tree с mode-aware feature gating;
- `ha_addon` не должен случайно получать весь full control plane или лишний operational surface;
- endpoint handler не должен сам решать, доступен ли он в конкретном mode.

### 17. Mode-aware availability matrix

Для каждого домена нужна явная matrix доступности по launch modes:

- `Read`
- `Command`
- `Jobs`
- `Webhooks`
- `Streams`
- `Admin/Observability`
- `Onboarding`

Эта matrix нужна не для формальности, а чтобы:

- контролировать exposure surface;
- тестировать bootstrap детерминированно;
- не допускать скрытых runtime-веток;
- понимать, что допустимо в `full`, `local`, `ha_addon`.

### 18. Capability model и contract audiences

Для principal-grade API недостаточно описывать только routes. Нужен capability-level артефакт.

Для каждой capability должны быть определены минимум:

- `capability_name`;
- `owner_domain`;
- `route_class`;
- `contract_audience`;
- `launch_modes`;
- `execution_model`;
- `idempotency_policy`;
- `operation_resource_required`;
- `auth_policy`;
- `observability_class`.

Рекомендуемые audiences:

- `public_read`;
- `operator_control`;
- `internal_platform`;
- `external_ingest`;
- `embedded_ha`.

### 19. Idempotency policy

Каждая command/job capability должна быть классифицирована как:

- strictly idempotent;
- conditionally idempotent;
- non-idempotent.

Обязательно определить:

- `idempotent: true | false | conditional`;
- `deduplication_key_source`;
- `repeat_response_semantics`;
- `already_running_behavior`;
- `retry_safe`.

Queued/job triggers должны иметь deduplication strategy и стандартизованное already-running поведение.

### 20. Operation resource model

Значимая async work должна быть first-class resource.

Для async/job/apply/run flows стандарт такой:

1. client вызывает command/job endpoint;
2. API возвращает `202 Accepted`;
3. в response есть `operation_id`;
4. client может прочитать status/result/events операции.

Минимальные operation endpoints:

- `GET /operations/{operation_id}`;
- `GET /operations/{operation_id}/events`;
- `GET /operations/{operation_id}/result`.

Минимальный operation contract:

- `operation_id`;
- `operation_type`;
- `status`;
- `requested_by`;
- `accepted_at`;
- `started_at`;
- `finished_at`;
- `request_id`;
- `correlation_id`;
- `causation_id`;
- `deduplication_key`;
- `result_ref`;
- `error_code`;
- `error_message`;
- `retryable`.

### 21. Concurrency и mutation semantics

Mutation surface должен иметь явную policy для конфликтов и повторов.

Нужно стандартизовать:

- optimistic concurrency support;
- stale update behavior;
- conflict error mapping;
- conditional request policy;
- version semantics.

Допустимые механизмы:

- version field, например `version` или `updated_at`;
- HTTP preconditions, например `ETag` / `If-Match`.

Запрещено:

- silent last-write-wins без явной политики;
- скрытая потеря изменений;
- случайный `409`, зависящий от конкретного handler.

### 22. Error taxonomy

Централизованный mapper недостаточен без единой taxonomy.

Минимальный набор transport error codes:

- `resource_not_found`;
- `validation_failed`;
- `invalid_filter`;
- `invalid_state_transition`;
- `concurrency_conflict`;
- `already_running`;
- `duplicate_request`;
- `rate_limited`;
- `policy_denied`;
- `mode_not_supported`;
- `capability_unavailable`;
- `integration_unreachable`;
- `provider_rejected`;
- `authentication_failed`;
- `authorization_denied`;
- `internal_error`.

Базовый error response contract:

- `code`;
- `message`;
- `details`;
- `retryable`;
- `request_id`;
- `correlation_id`;
- `docs_ref`;
- `operation_id`, если применимо.

### 23. Consistency / freshness semantics

Для analytical and derived read endpoints нужно явно декларировать data semantics.

Особенно это важно для:

- market data;
- news;
- signals;
- patterns;
- hypothesis;
- predictions;
- market structure snapshots.

Рекомендуемые поля:

- `generated_at`;
- `source_snapshot_at`;
- `staleness_ms`;
- `consistency`;
- `data_freshness_class`.

Рекомендуемые consistency classes:

- `strong`;
- `snapshot`;
- `eventual`;
- `derived`;
- `cached`.

Рекомендуемые freshness classes:

- `real_time`;
- `near_real_time`;
- `delayed`;
- `historical`;
- `unknown`.

### 24. Tracing contract

Tracing metadata должно быть частью transport contract для jobs, streams, webhooks и cross-domain workflows.

Обязательные identifiers:

- `request_id`;
- `correlation_id`;
- `causation_id`.

Они должны быть согласованно представлены в:

- логах;
- operation resources;
- success/error responses;
- stream events;
- webhook processing metadata.

### 25. Deployment profiles и HA-specific policy

Помимо launch modes нужен deployment-aware API policy.

Рекомендуемые deployment profiles:

- `platform_full`;
- `platform_local`;
- `ha_embedded`.

Для каждого profile должны быть заданы:

- allowed router groups;
- allowed capabilities;
- auth/access policy;
- stream policy;
- webhook policy;
- async operation policy;
- timeout class overrides;
- observability exposure;
- OpenAPI visibility.

Отдельное правило для `ha_addon`:

- embedded mode считается first-class profile;
- surface должен быть минимальным и строго контролируемым;
- HA-facing endpoints должны быть проверены на ingress/proxy compatibility и automation suitability.

### 26. Lifecycle, SLO, caching и review governance

HTTP/API governance должен учитывать эволюцию surface, а не только текущий код.

Нужно определить:

- stability class capability: `experimental`, `beta`, `stable`, `deprecated`;
- timeout/rate classes: `low_latency_read`, `heavy_analytical_read`, `mutation`, `async_trigger`, `stream`, `external_ingest`;
- caching/revalidation policy: `ETag`, `Cache-Control`, `stale-while-revalidate`, cache eligibility;
- formal endpoint review checklist для ownership, audience, launch mode, execution semantics, data semantics, errors, observability, OpenAPI и HA compatibility.

### 27. Governance scope по классам endpoint-ов

Не все governance primitives должны применяться одинаково ко всем endpoint-ам.

Обязательны для всех HTTP endpoints:

- shared `core/http`;
- `Pydantic` request/response contracts;
- dependency policy;
- error taxonomy и error body shape;
- router assembly policy;
- OpenAPI governance;
- launch-mode / profile awareness;
- standardized tags и `operationId`.

Обязательны только для async/job/operation flows:

- operation resource model;
- idempotency policy;
- deduplication policy;
- already-running behavior;
- tracing metadata в response contract.

Обязательны только для analytical/derived read endpoints:

- consistency/freshness semantics;
- caching/revalidation policy;
- page/cursor governance для растущих коллекций.

Обязательны только для mutable conflict-prone resources:

- concurrency semantics;
- explicit conflict contract.

### 28. Никакого fallback serialization

Если endpoint обещает typed response contract, он должен возвращать typed response contract.

Запрещено:

- `try: model_validate(...); except ValidationError: return item`;
- динамически возвращать то dataclass, то dict, то ORM object;
- скрывать contract drift внутри transport layer.

## Что делать по модулям

### P0: `market_structure` [done]

Файл:

- `backend/src/apps/market_structure/views.py`

Что не так:

- 23 endpoints в одном модуле
- смешаны plugins, onboarding, source CRUD, webhook registration, ingest, snapshots, jobs
- повторяющийся `try/except + commit + return`
- ingest/webhook surface рядом с обычным read API

Что делать:

- split на `read_endpoints`, `command_endpoints`, `onboarding_endpoints`, `webhook_endpoints`, `job_endpoints`
- ввести router prefix на module level
- вынести webhook token extraction / auth policy в `deps.py`
- свести множественные specialized onboarding POST handlers к более короткой plugin-driven surface, если бизнес-семантика это позволяет
- вынести snapshot presenter из view layer
- отдельно зафиксировать availability matrix для `webhooks`, `jobs`, `onboarding` в `full/local/ha_addon`

### P0: `control_plane` [done]

Файл:

- `backend/src/apps/control_plane/views.py`

Что не так:

- 17 endpoints, 10 private helper functions
- module выполняет роль presenter layer, auth layer и HTTP router одновременно
- header parsing / access-mode policy встроены прямо в views
- registry/routes/drafts/observability/audit смешаны в одном модуле

Что делать:

- split на `registry_endpoints`, `route_endpoints`, `draft_endpoints`, `observability_endpoints`
- вынести `require_control_actor` и related header parsing в `deps.py`
- вынести `_route_read`, `_draft_read`, `_audit_log_read` и related helpers в `presenters.py`
- зафиксировать единый command endpoint style для create/update/status/apply/discard
- убрать все non-endpoint helper functions из endpoint files
- первым прогнать модуль через `build_router(mode, profile)` и mode-aware exposure policy, потому что именно тут сильнее всего отличается `full/local/ha_addon`
- отдельно определить concurrency semantics и operation model для apply/update/status-change flows

### P0: `signals` [done]

Файл:

- `backend/src/apps/signals/views.py`

Что не так:

- один giant read-only module на 16 endpoints
- внутри смешаны signals, decisions, market decisions, final signals, backtests, strategies
- resource group boundaries неочевидны

Что делать:

- split как минимум на:
  - `signal_read_endpoints.py`
  - `decision_read_endpoints.py`
  - `final_signal_read_endpoints.py`
  - `backtest_read_endpoints.py`
  - `strategy_read_endpoints.py`
- определить, какие endpoints остаются под `/signals/*`, а какие должны стать отдельными top-level resources
- явно зафиксировать canonical ownership для signal surface и derived decision surface

### P0: `news` [done]

Файл:

- `backend/src/apps/news/views.py`

Что не так:

- source CRUD, item reads, onboarding и job triggers в одном файле
- telegram onboarding flow живет рядом с обычным source API
- repeated exception mapping

Что делать:

- split на `plugin_read_endpoints`, `source_endpoints`, `item_endpoints`, `job_endpoints`, `telegram_onboarding_endpoints`
- ввести единый queued response contract
- унифицировать command exception translation
- отдельно определить, какие onboarding/job surfaces доступны в `ha_addon`, а какие только в `full/local`
- ввести idempotent job-trigger policy и operation resource model для backfill/refresh flows

### P1: `market_data` [done]

Было:

- `backend/src/apps/market_data/views.py`

Что было не так:

- fallback serialization через `ValidationError`
- manual payload conversion в `_coin_response` / `_price_history_response`
- reads, commands и jobs пока еще лежат вместе
- task trigger behavior (`taskiq_backfill_event`) виден прямо из endpoint

Что сделано:

- HTTP surface переведен в `backend/src/apps/market_data/api/*`
- `views.py` удален; домен экспортирует только `build_router(mode, profile)`
- read, command и job handlers разведены по отдельным endpoint modules
- strict typed presenters заменили fallback-style serialization
- task trigger side effect вынесен в dedicated dependency/command adapter
- contract tests фиксируют отсутствие legacy `market_data.views` import path

### P1: `hypothesis_engine` [done]

Было:

- `backend/src/apps/hypothesis_engine/views.py`

Что было не так:

- prompts, reads, jobs и SSE stream в одном модуле
- stream-specific Redis/group logic сидит прямо в HTTP file

Что сделано:

- HTTP surface переведен в `backend/src/apps/hypothesis_engine/api/*`
- `views.py` удален; домен экспортирует только `build_router(mode, profile)`
- prompt commands, reads, jobs и stream handlers разведены по отдельным endpoint modules
- SSE runtime mechanics вынесены в dedicated `stream_adapter.py`
- `ha_embedded` не монтирует jobs и stream surface
- evaluate job теперь возвращает typed accepted response, а contract tests фиксируют отсутствие legacy `hypothesis_engine.views` import path

### P1: `patterns` [done]

Было:

- `backend/src/apps/patterns/views.py`

Что было не так:

- admin mutation endpoints и public analytics reads смешаны

Что сделано:

- HTTP surface переведен в `backend/src/apps/patterns/api/*`
- `views.py` удален; домен экспортирует только `build_router(mode, profile)`
- admin mutation handlers и public analytics reads разведены по `command_endpoints.py` и `read_endpoints.py`
- error mapping стандартизован через typed `ApiError` contracts
- contract tests фиксируют mode-agnostic router и отсутствие legacy `patterns.views` import path

### P2: `indicators` [done]

Было:

- `backend/src/apps/indicators/views.py`

Что было не так:

- module маленький, но уже есть cross-domain coupling: `PatternQueryService` используется прямо из indicator HTTP surface

Что сделано:

- HTTP surface переведен в `backend/src/apps/indicators/api/*`
- `views.py` удален; домен экспортирует только `build_router(mode, profile)`
- cross-domain read composition для `/market/cycle` скрыта за dedicated `IndicatorReadFacade`
- contract tests фиксируют mode-agnostic router и отсутствие legacy `indicators.views` import path

### P2: `portfolio` [done]

Было:

- `backend/src/apps/portfolio/views.py`

Что сделано:

- HTTP surface переведен в `backend/src/apps/portfolio/api/*`
- `views.py` удален; домен экспортирует только `build_router(mode, profile)`
- read handlers теперь получают только `PortfolioQueryService` через standardized deps/presenters path
- contract tests фиксируют mode-agnostic router и отсутствие legacy `portfolio.views` import path

### P2: `predictions` [done]

Было:

- `backend/src/apps/predictions/views.py`

Что сделано:

- HTTP surface переведен в `backend/src/apps/predictions/api/*`
- `views.py` удален; домен экспортирует только `build_router(mode, profile)`
- read handlers теперь используют `PredictionQueryService` через standardized deps/presenters path
- contract tests фиксируют mode-agnostic router и отсутствие legacy `predictions.views` import path

### P2: `system` [done]

Было:

- `backend/src/apps/system/views.py`

Что было не так:

- health/status logic partially assembled in endpoint module

Что сделано:

- HTTP surface переведен в `backend/src/apps/system/api/*`
- `views.py` удален; домен экспортирует только `build_router(mode, profile)`
- source/rate-limit status assembly вынесена в `SystemStatusFacade`, так что в endpoint file остались только handlers
- health response переведен на typed Pydantic contract
- contract tests фиксируют mode-agnostic router и отсутствие legacy `system.views` import path
- оставить `views` только как transport layer

## Предлагаемый порядок работ

1. Ввести `src/core/http/` как общий transport foundation: contracts, errors, pagination, responses, presenters, command executor, launch modes.
2. Ввести root API structure: `src/api/router.py` + `src/api/v1/router.py`.
3. Зафиксировать `LaunchMode`, deployment profiles, mode-aware router assembly, availability matrix и capability matrix по доменам.
4. Ввести domain `api/` package standard и правило одного публичного router entrypoint `build_router(mode, profile)`.
5. Зафиксировать operation resource model, idempotency policy, error taxonomy и tracing contract для async/job flows.
6. Зафиксировать consistency/freshness/caching policy для analytical read endpoints.
7. Перевести `control_plane` как первый mode-sensitive и transport-heavy модуль.
8. Перевести `market_structure`, отдельно разрезав read / commands / onboarding / webhooks / jobs.
9. Перевести `news`, отдельно разведя source API, item reads, jobs и onboarding.
10. Разбить `signals` на несколько bounded read routers и проверить URL semantics.
11. Active domain HTTP cutover закрыт; дальше остаются только governance hardening tasks вроде OpenAPI diff control, capability matrix automation и review checklist enforcement.

## Правила миграции

- не строить новый `api/` layout без `src/core/http/`, иначе проект просто переизобретет pagination/errors/responses в каждом домене;
- не делать compatibility wrappers между старым `views.py` и новой `api/` структурой;
- не держать в endpoint modules ничего, кроме async endpoint functions и router declarations;
- не использовать `Depends(...)` для transport-validation helper-ов: через dependency в handler должен приходить уже собранный runtime service/facade;
- request/response contracts переводить на `Pydantic` сразу, а не оставлять mixed `dict/dataclass/ORM` path;
- не делать operation resource model обязательным для тривиальных sync CRUD endpoints без реальной async semantics;
- не тащить consistency/freshness metadata в справочники и примитивные административные списки, где это не дает новой информации;
- не переносить helper-функции один в один без переосмысления responsibility;
- если endpoint module уже giant, резать его сразу на несколько transport modules;
- не оставлять mapping helpers в router module, если они содержат domain knowledge;
- не оставлять `kiq()`/queue dispatch import-логику размазанной по всем endpoint files без общего command/job adapter pattern;
- не тащить fallback serialization behavior;
- не смешивать public reads и operational mutations без явной причины;
- не менять внешний URL без отдельного решения и migration note;
- после каждого доменного среза контролировать OpenAPI diff и mode-specific exposure.

## Definition of Done

Endpoint layer считается доведенным до целевого стандарта, когда:

- в проекте есть `src/core/http/` как единый transport foundation;
- в проекте есть один root API tree `/api/v1`;
- каждый домен имеет `api/` package и один публичный router entrypoint;
- giant `views.py` modules исчезли;
- endpoint files содержат только async handlers;
- `Depends(...)` в handler-ах используется только для runtime services/facades и стандартизованных access dependencies;
- request/response contracts выражены через `Pydantic` schemas;
- dependency wiring вынесен в `deps.py`;
- error mapping вынесен и стандартизован через shared base + domain-local extension;
- commit policy для HTTP commands централизована через `command_executor`;
- prefix, tags и `operationId` policy унифицированы;
- transport mapping вынесен из router modules в presenters;
- queued/job/webhook/stream endpoints отделены от обычного read API;
- pagination/filter/sort policy унифицирована;
- response contracts стали строгими и typed;
- capability matrix задокументирована;
- error taxonomy стандартизована на уровне code/message/details/retryable;
- для async/job/apply/run flows внедрен operation resource model;
- для async/job flows задокументированы idempotency и already-running semantics;
- tracing metadata стандартизованы в operations/errors/streams там, где это требуется;
- для analytical/derived read endpoints зафиксированы consistency/freshness semantics;
- deployment profiles задокументированы и связаны с availability policy;
- каждый домен имеет documented availability matrix для `full`, `local`, `ha_addon`;
- bootstrap собирает router tree mode-aware и не экспонирует лишний surface в `ha_addon`;
- OpenAPI описывает success/error contracts, pagination, queued responses и security requirements;
- endpoint tests покрывают новый surface по router categories;
- есть bootstrap tests на разные launch modes и tests на mode-specific router exposure.
