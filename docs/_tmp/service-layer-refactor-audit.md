# IRIS Service And Analytical Engine Refactor Audit And Standard

## Цель

Закрыть последний крупный архитектурный слой после persistence и HTTP:

- стандартизовать service layer;
- стандартизовать analytical/mathematical engine layer;
- убрать service-god modules;
- зафиксировать строгие runtime rules;
- отделить orchestration от transport и persistence;
- отделить orchestration от pure math/analytics;
- перевести active service path на typed contracts;
- убрать ad-hoc `dict[str, object]` результаты и служебные compatibility-паттерны;
- сделать service layer предсказуемым для API, workers, TaskIQ jobs и control-plane orchestration.

Это не cosmetic cleanup.

Нужен прямой cutover к единому стандарту:

- **async-first**
- **class-first**
- **async-class-first**
- **typed contracts**
- **caller-owned transaction boundary**
- **services orchestrate, repositories persist, query services project**
- **engines compute, services orchestrate**
- **no god-services**
- **no transport payload shaping inside services**
- **no hidden data fetching from analytical engines**
- **no direct infra leakage without explicit port/adapter**

## Текущее состояние

Persistence и HTTP стандартизованы. Последний крупный архитектурный хвост теперь находится в service layer и в неформализованном analytical engine layer.

Самые тяжелые active service modules по размеру:

- `backend/src/apps/market_structure/services.py` — `1406` LOC
- `backend/src/apps/signals/services.py` — `816` LOC
- `backend/src/apps/control_plane/services.py` — `763` LOC
- `backend/src/apps/portfolio/services.py` — `699` LOC
- `backend/src/apps/market_data/services.py` — `619` LOC
- `backend/src/apps/cross_market/services.py` — `599` LOC
- `backend/src/apps/indicators/services.py` — `538` LOC
- `backend/src/apps/patterns/task_service_runtime.py` — `533` LOC
- `backend/src/apps/news/services.py` — `530` LOC
- `backend/src/apps/predictions/services.py` — `438` LOC

Это уже не “один-два неудобных файла”, а системный service-governance gap.

## Главные проблемы

### 0. Нет формального split-а между orchestration services и pure analytical engines

Это сейчас главный архитектурный риск для math-heavy domains.

Проблема выглядит так:

- сервис и загружает данные;
- и принимает orchestration decisions;
- и считает скоринги/кластеризацию/агрегации;
- и сам же сохраняет результат;
- и иногда сразу формирует summary payload.

В такой форме:

- математическая логика не является самостоятельным контрактом;
- ее трудно unit-test-ить без БД и runtime wiring;
- изменение формул слишком тесно связано с repositories/UoW/event side effects;
- невозможно легко переиспользовать один и тот же engine в HTTP/job/runtime flows.

Для IRIS это критично, потому что домены `signals`, `indicators`, `cross_market`, `predictions`, `patterns`, `anomalies` и часть `portfolio`/`market_structure` содержат реальную вычислительную логику, а не просто CRUD orchestration.

### 1. Service modules часто стали новым application god layer

Типичные симптомы:

- в одном модуле смешаны command orchestration, jobs, provisioning, side effects и result shaping;
- один class знает слишком много bounded-context деталей;
- один service отвечает сразу за mutation, analytics, event publication и summary payload.

Примеры:

- `control_plane/services.py`
- `market_structure/services.py`
- `signals/services.py`
- `portfolio/services.py`

### 2. Typed service result contracts внедрены непоследовательно

В части доменов уже есть dataclass-based results, но во многих местах сервисы по-прежнему возвращают:

- `dict[str, object]`
- `{"status": "ok" | "skipped" | "error"}`
- summary payload через `to_summary()`

Это видно в:

- `market_data/services.py`
- `news/services.py`
- `market_structure/services.py`
- `cross_market/services.py`
- `patterns/task_service_*`

Это плохо, потому что:

- caller вынужден знать ad-hoc status vocabulary;
- нет единого typed error/result contract;
- service становится transport-like instead of application-like.

### 3. Service layer местами все еще знает слишком много про низкоуровневую infra форму

Сигналы проблемы:

- `AsyncSession` в service constructors или helper signatures;
- module-level helper functions для write path;
- raw publish/cache side effects прямо в service body;
- `SimpleNamespace` или payload proxies для downstream runtime messages.

Примеры:

- `market_data/services.py`
- `control_plane/services.py`

### 4. Presentation shaping течет в service layer

Сейчас часть services возвращает не domain/application result, а уже “готовую summary-форму”:

- `to_summary()`
- `to_payload()`
- ad-hoc dict rows

Это повторяет старую проблему transport leakage, только на уровень ниже.

### 5. Side effects не везде оформлены как отдельный service concern

Сейчас side effects уже часто deferrable через `after_commit`, но не везде формализованы как отдельные output ports/dispatchers.

Нужен единый стандарт:

- command service меняет состояние;
- output dispatcher/port публикует события, cache invalidation, messages;
- side effects регистрируются как post-commit work.

### 6. Cross-domain coupling в service layer нормализован не до конца

Сервисам уже нельзя напрямую владеть transport/persistence, но остается риск:

- тащить чужие repositories/models;
- собирать cross-domain snapshots вручную;
- использовать “удобный” helper соседнего домена вместо явного facade/query/service boundary.

### 7. Module/package layout для services не стандартизован

Сейчас есть все варианты сразу:

- один giant `services.py`
- `task_services.py`
- `task_service_runtime.py`
- `task_service_bootstrap.py`
- side-effect dispatcher внутри того же файла

Это затрудняет:

- ownership;
- review;
- naming discipline;
- поиск orchestration hotspots.

## Главная архитектурная модель: два слоя

Для math-heavy use cases стандарт должен быть не “service layer”, а **service + engine**.

### Layer A — Orchestration service

Отвечает за:

- загрузку входных данных через repositories/query services;
- нормализацию и сборку typed engine input;
- вызов pure analytical engine;
- сохранение результата;
- регистрацию post-commit side effects;
- возврат typed application result.

### Layer B — Analytical engine

Отвечает только за:

- вычисления;
- scoring;
- ranking;
- clustering;
- signal fusion math;
- policy evaluation;
- detection logic;
- derivation of analytical outcomes from already prepared inputs.

Engine ничего не знает про:

- БД;
- Redis;
- UoW;
- HTTP;
- TaskIQ;
- ORM;
- logging transports;
- runtime dispatch.

Коротко:

- **service loads and persists**
- **engine computes**

### Async-class-first rule

Это отдельное обязательное правило, а не stylistic preference.

Для active application path по умолчанию:

- orchestration capabilities оформляются как async classes;
- service boundary выражается class contract-ом;
- public operations оформляются async methods;
- dependency graph собирается вокруг class-based services/engines, а не вокруг россыпи module-level helper functions.

Запрещено по умолчанию:

- строить active orchestration path на module-level async helper functions как на основном contract-е;
- держать procedural “service modules” без явного class boundary;
- плодить ad-hoc function chains, которые фактически играют роль service layer без явного ownership.

Допустимое исключение:

- pure analytical math/transform functions внутри engine/support layer;
- tiny pure helpers в `support.py` / `math.py` / `policies.py`;
- но не orchestration boundary.

## Целевой service and engine standard

## 1. Service categories

В проекте должны существовать четкие service categories.

### Application command services

Для synchronous write/use-case orchestration:

- create/update/delete/apply/approve/recalculate/refresh

Форма по умолчанию:

- async class with explicit constructor dependencies

Примеры имен:

- `RouteManagementService`
- `TopologyDraftService`
- `PortfolioService`

### Task/job services

Для background execution paths:

- scheduled jobs;
- event-triggered orchestration;
- TaskIQ workloads;
- heavy recalculation flows.

Форма по умолчанию:

- async class with explicit constructor dependencies

Примеры имен:

- `PatternRealtimeService`
- `MarketDataHistorySyncService`
- `SignalHistoryService`

### Provisioning/integration services

Для bounded integration workflows:

- onboarding;
- source provisioning;
- provider-specific setup.

Форма по умолчанию:

- async class with explicit constructor dependencies

Примеры:

- `TelegramSessionOnboardingService`
- `MarketStructureSourceProvisioningService`

### Side-effect dispatchers / output adapters

Для post-commit external effects:

- event publishing;
- cache writes/invalidation;
- stream messages;
- broker notifications.

Примеры:

- `SignalFusionSideEffectDispatcher`
- `PortfolioSideEffectDispatcher`

### Pure analytical engines

Если модуль реализует math/analytics/policy logic и не делает IO, он должен жить не в service class, а в engine layer.

Предпочтительные responsibilities:

- scoring
- aggregation
- feature extraction
- signal fusion logic
- anomaly detection
- ranking
- regime classification
- clustering
- strategy evaluation

Предпочтительная форма:

- pure functions by default
- thin class wrapper only when shared configuration/strategy injection is really needed

То есть `async-class-first` относится к orchestration layer, а не к pure math layer.

### Pure support/policy modules

Если логика stateless и не оркестрирует repositories/UoW, она не должна жить в service class.

Для этого существуют:

- `support.py`
- `domain/*.py`
- `policies.py`
- `scoring.py`
- `semantics.py`

## 2. Analytical engine contract

Analytical engine может:

- принимать только already prepared typed inputs;
- использовать pure helper functions;
- возвращать typed result contract;
- принимать explicit config/weights/thresholds as values;
- использовать deterministic math over provided data.

Analytical engine не должен:

- дозапрашивать данные;
- принимать repository/query/uow/session dependencies;
- вызывать network/Redis/TaskIQ/provider SDK;
- читать `utc_now()`/`datetime.now()`/random state неявно;
- логировать transport/runtime payloads как часть business contract;
- возвращать ORM objects, transport DTO или `dict[str, object]`.

### Нормальная execution chain

1. query/repository layer загружает данные
2. orchestration service собирает typed engine input
3. engine считает результат
4. service сохраняет результат и регистрирует side effects
5. caller commit-ит transaction

### Ключевое правило

Если engine требует еще один запрос к БД, значит граница выбрана неправильно.

Нужно:

- либо расширить query/repository projection;
- либо собрать richer input model до вызова engine;
- но не тащить IO внутрь analytical core.

## 3. Engine input/output policy

Для engine layer нужны отдельные typed contracts, не равные persistence shape и не равные HTTP shape.

Правильно:

- `SignalFusionInput`
- `SignalFusionOutput`
- `AnomalyDetectionInput`
- `AnomalyDetectionResult`
- `MarketFlowInput`
- `MarketFlowResult`

Неправильно:

- передавать ORM entity;
- передавать raw `dict`;
- передавать Pydantic HTTP schema;
- давать engine прямой доступ к repository/query service.

Предпочтительный тип:

- `@dataclass(frozen=True, slots=True)`

### Numeric policy

Для каждого engine contract числовая модель должна быть явной:

- либо `float`
- либо `Decimal`
- либо `int`-based scaled values

Смешение numeric semantics внутри engine без явного boundary conversion запрещено.

### Time policy

Время должно быть нормализовано до вызова engine:

- timezone-aware only;
- timestamps prepared in service/query layer;
- engine не нормализует транспорт/БД timestamps “по пути”, если это не часть самой аналитической логики.

## 4. Service responsibility contract

Service может:

- принять typed command/context;
- загрузить mutable state через repositories;
- вызвать domain policies/support functions;
- оркестрировать несколько repository operations;
- вызвать explicit read/query facade, если use-case требует проверки/lookup;
- зарегистрировать post-commit side effects;
- вернуть typed result contract;
- поднять typed domain/application exception.

Service public boundary по умолчанию выражается class method-ами, а не набором свободных async functions.

Service не должен:

- принимать `Request`, `Response`, `HTTPException`, Pydantic transport DTO as transport concern;
- делать SQL/ORM orchestration вне repository/query boundaries;
- решать OpenAPI/HTTP status semantics;
- возвращать transport payload;
- directly own `commit()`/`rollback()`;
- directly own queue/broker/runtime lifecycle;
- работать как “god facade for entire domain”.

Дополнительно для math-heavy flows:

- service должен быть адаптером между IO-layer и engine layer;
- service не должен тащить математику в себя, если ее можно вынести в pure engine;
- service не должен превращаться в набор “немного загрузили, немного посчитали, немного еще догрузили”.

## 5. Dependency injection policy

Service разрешено инжектить:

- `BaseAsyncUnitOfWork`
- domain repositories
- query services/read facades
- explicit side-effect dispatcher/output port
- pure domain support modules/policies
- configuration values
- explicit integration adapters

Service запрещено инжектить напрямую:

- `fastapi.Request`, `fastapi.Response`, `HTTPException`
- transport DTO ради самого DTO
- raw `AsyncSession` как основной dependency для active write path
- raw Redis clients
- raw TaskIQ clients / `kiq()` calls
- raw provider SDK clients без adapter boundary
- repositories/models соседнего bounded context без explicit facade boundary

Примечание:

- `flush()` внутри service допустим, если нужен generated ID / ordering / locking semantics;
- `AsyncSession` допустим только внутри infrastructure adapter или как временный audit item на миграцию, но не как целевой service contract.

Конструктор service/engine boundary должен быть явным. Скрытая сборка dependency graph через module globals или function-local factories запрещена.

Engine разрешено инжектить только:

- config values;
- pure policy objects;
- pure scorer/calculator helpers;
- deterministic lookup tables.

## 6. Transaction policy

Единое правило:

- caller owns `commit()`
- service mutates state
- service may `flush()`
- service may `add_after_commit_action(...)`
- service never hides final transaction boundary

Это уже соответствует persistence/HTTP standard и должно быть закреплено для service layer как mandatory rule.

## 7. Result contract policy

По умолчанию service methods возвращают typed result objects:

- `@dataclass(frozen=True, slots=True)` для application/job result contracts
- explicit typed tuples only when semantics are trivial and documented

Запрещено по умолчанию:

- `dict[str, object]`
- `{"status": ...}`
- `to_summary()` как основной public contract
- return shape, который caller потом должен “угадывать”

Правильный стиль:

- `CreateRouteResult`
- `RefreshSourceHealthResult`
- `PredictionEvaluationResult`
- `HistorySyncBatchResult`

Если нужен transport payload:

- presenter на HTTP layer или worker/reporting adapter строит его отдельно.

Для engine layer правило то же:

- engine возвращает typed result;
- engine поднимает typed domain/engine exception;
- engine не сигналит ошибку через raw dict status.

## 8. Error policy

Service не должен сигналить ошибки через payload status.

Нужно:

- `return typed result` для valid business outcome
- `raise typed application/domain exception` для invalid outcome

Примеры:

- `SourceNotFound`
- `SourceDisabled`
- `ConcurrencyConflict`
- `InvalidStateTransition`
- `AlreadyRunning`

Допустимо возвращать typed skipped/no-op result, если это реально штатная бизнес-семантика, а не ошибка.

Например:

- `HistorySyncResult(status="skipped", reason="pending_backfill", ...)`

Но это должен быть typed result object, а не ad-hoc dict.

## 9. Side-effect policy

Все значимые внешние effects должны идти через explicit output boundary:

- event publish
- cache invalidation/write
- runtime message publish
- webhook callback
- operation updates

Service body не должен хаотично публиковать side effects inline.

Целевой flow:

1. service computes state change
2. service prepares side-effect intent
3. service registers after-commit action or hands intent to dispatcher
4. caller commits
5. side effects execute post-commit

## 10. Cross-domain policy

Service может зависеть от другого домена только через:

- query service
- application facade
- explicit integration adapter
- pure support contract

Service не должен:

- писать напрямую в repository чужого bounded context без явного architectural decision;
- ходить в ORM model соседнего домена как “удобную shortcut”.

## 11. Testing policy for analytical engines

Engine layer должен быть самым легко тестируемым слоем в системе.

Обязательно:

- unit tests без БД;
- table-driven tests на branch behavior;
- deterministic fixtures/golden cases;
- edge-case tests для NaN/empty input/boundary windows/threshold crossings;
- regression tests на формулы и ranking order.

Предпочтительно:

- property-style tests там, где есть инварианты;
- explicit fixtures для tricky market scenarios;
- snapshot tests только если result contract стабилен и понятен.

Service tests отдельно проверяют:

- correct input assembly for engine;
- persistence/save semantics;
- post-commit side effects;
- exception mapping between engine/application layers.

## 12. Logging policy

Service layer должен логироваться так же строго, как persistence и HTTP.

Минимальный structured logging:

### DEBUG

- service method entry
- domain
- operation
- mode: `read-check` / `write` / `job`
- key ids and filters
- branch selection
- flush / lock points
- batch sizes

### INFO

- successful state-changing operation
- published operation summary
- important skipped/no-op business outcomes

### WARNING

- degraded fallback path
- suspicious large batch
- expensive retry / duplicate path

### ERROR

- unexpected domain/application failures
- mapping failures
- external adapter failures

Engine layer сам по себе не обязан быть heavily logged.

По умолчанию:

- orchestration service логирует вход/выход и важные branch decisions;
- engine возвращает explainability/debug data как typed field, если это реально нужно;
- но engine не превращается в IO-heavy logger.

## 13. Module and package layout

Если домен простой, допускается один `services.py`.

Но даже в этом случае active orchestration boundary должен оставаться class-based.

Но если выполняется хотя бы одно условие, домен обязан перейти на `services/` package:

- module > `300` LOC
- class > `250` LOC
- в одном module больше `3` service classes
- module смешивает command + jobs + provisioning + side effects
- есть явный split between sync command flow and background orchestration

Целевая service структура:

```text
src/apps/<domain>/services/
  __init__.py
  command_service.py
  job_service.py
  provisioning_service.py
  side_effects.py
  results.py
  ports.py
  exceptions.py
```

Целевая engine структура для math-heavy domain:

```text
src/apps/<domain>/engines/
  __init__.py
  contracts.py
  <capability>_engine.py
  <capability>_math.py
  <capability>_policies.py
  explainability.py
```

Допустимы более предметные имена:

- `history_sync_service.py`
- `fusion_service.py`
- `draft_service.py`
- `route_management_service.py`

Но giant `services.py` как контейнер на все случаи жизни должен исчезать.

Для простых случаев допустимо:

- `analytics.py`
- `scoring.py`
- `policies.py`

Но если analytical logic уже выросла, giant `analytics.py` так же плох, как giant `services.py`.

## 14. Naming policy

Service names должны выражать capability, а не vague “manager/engine/helper”.

Хорошо:

- `MarketDataHistorySyncService`
- `RouteManagementService`
- `PredictionEvaluationService`
- `SignalFusionService`

Плохо:

- `DataService`
- `CommonService`
- `HelperService`
- `EngineService`

Method names тоже должны быть capability-driven:

- `create_route(...)`
- `apply_draft(...)`
- `refresh_source_health(...)`
- `evaluate_market_decision(...)`
- `sync_history(...)`

Избегать:

- `process(...)`
- `run(...)`
- `handle(...)`

если из названия неясно, что именно происходит.

Для engine names:

Хорошо:

- `SignalFusionEngine`
- `MarketFlowEngine`
- `PredictionEvaluationEngine`
- `AnomalyDetectionEngine`

Плохо:

- `Utils`
- `CalculatorService`
- `Manager`
- `Processor`

## 15. Testing policy

Каждый service contract должен иметь:

- typed result contract tests
- business branch tests
- transaction/flush behavior tests, где важно
- post-commit side-effect tests, где важно
- error contract tests

Дополнительно:

- service tests не должны проверять HTTP payload shape
- service tests не должны зависеть от transport DTO
- если service split-ится, tests тоже режутся по capability, а не по giant module

Отдельно:

- engine tests не должны поднимать UoW/session;
- service tests не должны повторять всю математику engine внутри assertions, только проверять wiring и invariants;
- integration tests должны проходить по цепочке `load -> engine -> persist`, а не подменять architectural split.

## 16. Current migration priorities

### P0 — introduce explicit engine layer on math-heavy domains

- `backend/src/apps/signals/services.py`
- `backend/src/apps/indicators/services.py`
- `backend/src/apps/cross_market/services.py`
- `backend/src/apps/predictions/services.py`
- `backend/src/apps/patterns/task_service_runtime.py`
- `backend/src/apps/anomalies/services/anomaly_service.py`

Главная цель:

- вынести pure scoring/detection/ranking/fusion math из orchestration services;
- зафиксировать typed engine input/output contracts;
- запретить hidden fetches inside analytical logic.

### P0 — split immediately

- `backend/src/apps/market_structure/services.py`
- `backend/src/apps/control_plane/services.py`
- `backend/src/apps/signals/services.py`

Причины:

- размер
- смешение responsibilities
- side effects + orchestration + result shaping в одном месте

### P1 — typed result contract cleanup

- `backend/src/apps/market_data/services.py`
- `backend/src/apps/news/services.py`
- `backend/src/apps/cross_market/services.py`
- `backend/src/apps/patterns/task_service_runtime.py`
- `backend/src/apps/patterns/task_service_market.py`
- `backend/src/apps/patterns/task_service_history.py`
- `backend/src/apps/patterns/task_service_context.py`
- `backend/src/apps/patterns/task_service_decisions.py`
- `backend/src/apps/patterns/task_service_bootstrap.py`

Главная цель:

- убрать `dict[str, object]` / `status` payloads
- ввести typed result dataclasses

### P1 — engine input model cleanup

- `backend/src/apps/signals/services.py`
- `backend/src/apps/indicators/services.py`
- `backend/src/apps/anomalies/services/anomaly_service.py`
- `backend/src/apps/predictions/services.py`

Главная цель:

- перестать скармливать engine-bound logic ORM/raw repo shape;
- ввести explicit analytical input dataclasses;
- сделать math-core unit-testable without DB.

### P1 — remove direct session-shaped helpers from service layer

- `backend/src/apps/market_data/services.py`
- `backend/src/apps/control_plane/services.py`

Главная цель:

- вытеснить `AsyncSession` из active service contracts
- перенести helper-level persistence orchestration в repositories/support modules

### P2 — service package split after contract cleanup

- `backend/src/apps/portfolio/services.py`
- `backend/src/apps/indicators/services.py`
- `backend/src/apps/predictions/services.py`
- `backend/src/apps/news/services.py`
- `backend/src/apps/cross_market/services.py`

## 17. Definition of done

Service layer считается доведенным до целевого стандарта только если:

- active write/task orchestration идет через small class-based async services;
- analytical logic вынесена в explicit pure engine layer там, где она не является trivial;
- giant `services.py` cut into package where needed;
- service contracts typed;
- engine contracts typed;
- `dict[str, object]` result payloads removed from active service public methods;
- services no longer own HTTP concerns;
- services no longer own persistence internals beyond UoW/repository contracts;
- engines do not fetch or persist anything;
- services no longer own raw side-effect mechanics inline;
- cross-domain dependencies go only through explicit boundaries;
- tests cover typed results, branch semantics and post-commit behavior;
- engine tests run without DB/runtime wiring.

## 18. Главный вывод

Persistence и HTTP уже приведены к единому стандарту.

Service layer и analytical engine layer — последние слои, где проект еще может скатиться обратно в architectural blur, даже при чистых repositories и clean routers.

Следующий этап должен быть не “подчистить пару сервисов”, а ввести такой же жесткий governance standard, какой уже был введен для:

- persistence
- HTTP/API

И только после этого последовательно cutover-ить service hotspots по приоритету.
