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
- превратить ключевые архитектурные правила из markdown в CI-enforced policy;
- завести эталонный reference module и живой architecture scorecard;
- сделать direct cutover service layer на финальную форму без промежуточных compatibility stages;
- сделать service layer предсказуемым для API, workers, TaskIQ jobs и control-plane orchestration.

Это не cosmetic cleanup.

Так как persistence, HTTP и соседние слои уже приведены к единому стандарту, service layer нельзя тащить через промежуточные состояния.

Здесь нужен clean final cutover:

- внешние контракты уже вычищенных слоев не ломаются;
- временные service-compatible wrappers не становятся новой нормой;
- каждый hotspot переводится сразу в целевую service/engine форму, а не через “сначала чуть-чуть лучше”.

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
- **architecture rules live in CI, not only in markdown**
- **direct cutover to final service shape, no interim compatibility stages**

## Текущее состояние

Persistence, HTTP и planned service-layer governance уже стандартизованы.

Фактическое post-cutover состояние на `2026-03-14`:

- все stage из `docs/iso/service-layer-execution-plan.md` выполнены;
- planned hotspot domains `signals`, `predictions`, `cross_market`, `control_plane`, `market_structure`, `patterns/task_service_runtime`, `anomalies`, `market_data`, `news`, `indicators` и `portfolio` переведены в финальную service/engine форму;
- architecture CI suite, generated scorecard, ADR package, runtime policies и performance budgets уже живут в репозитории и pipeline;
- остаточный service-layer debt больше не размазан по всем hotspots и теперь локализован в `patterns` и частично `hypothesis_engine`.

Текущий generated snapshot из architecture scorecard:

- `patterns` — `2173` aggregated service LOC, `23` policy violations;
- `market_structure` — `1036` aggregated service LOC, `clean`;
- `signals` — `917` aggregated service LOC, `clean`;
- `control_plane` — `719` aggregated service LOC, `clean`;
- `cross_market` — `685` aggregated service LOC, `clean`;
- `hypothesis_engine` — `388` aggregated service LOC, `2` policy violations;
- все остальные planned cutover domains находятся в статусе `clean`.

Ниже в разделах `0-20` сохранен pre-cutover audit baseline, который объясняет, почему этот план вообще был нужен. Актуальный executed state зафиксирован в разделах `21-26`.

## Главные проблемы

Ниже перечислен исторический baseline проблем, с которого стартовал refactor. Это не текущий scorecard-срез, а исходная мотивация и стандарт, который затем был реализован.

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

### 8. Правила пока живут в документе сильнее, чем в pipeline

Сейчас стандарт описан хорошо, но enforcement слабый:

- engine purity не проверяется CI;
- giant module thresholds не валят build;
- запрет на `dict[str, object]` / `{"status": ...}` не охраняется автоматически;
- direct `AsyncSession` leakage в service contract не блокируется тестом;
- cross-domain shortcuts не фиксируются архитектурной политикой.

Пока правило живет только в markdown, оно advisory. Для service rewrite этого уже недостаточно.

### 9. Структурные правила описаны сильнее, чем semantic и operational invariants

Структура уже понятна, но для аналитических сервисов этого мало.

Нужно формализовать не только форму, но и поведение:

- какие invariants обязаны быть истинны на boundary;
- что считается deterministic result;
- какие job/service операции обязаны быть reentrant;
- что считается safe retry;
- когда sync path обязан уйти в job path;
- как explainability и reproducibility входят в контракт, а не висят в логах.

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

### Semantic invariant policy

Engine contract должен фиксировать предметные invariants явно, а не оставлять их “по договоренности”.

Минимальный baseline для analytical domains:

- timestamps отсортированы и normalized до engine boundary;
- weights суммируются до `1 ± epsilon`, если домен использует нормированные веса;
- `NaN` и `inf` запрещены на boundary;
- одинаковый input + одинаковые `PolicyVersion` / `ModelVersion` / `WeightsVersion` дают идентичный result;
- tie-break при равенстве score детерминирован и задокументирован;
- каждое threshold crossing, влияющее на outcome, имеет explainability reason.

Service отвечает за подготовку и валидацию boundary shape.

Engine отвечает за deterministic evaluation этих invariants внутри вычислительного контракта.

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
- `AsyncSession` допустим только внутри infrastructure adapter; в service constructor или public helper signature это всегда violation, а не переходная норма.

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

Эти thresholds являются build-breaking policy, а не рекомендацией для “когда-нибудь потом”.

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

## 16. Architecture CI policy

Все ключевые service/engine rules должны жить не только в audit markdown, но и в `backend/tests/architecture/` как build-breaking checks.

Обязательные automated guards:

- `engines/*` не импортируют `sqlalchemy`, `fastapi`, `redis`, `taskiq`, `httpx` и provider SDK;
- service public methods не возвращают `dict[str, object]` и `{"status": ...}`;
- service constructors не принимают `AsyncSession`;
- giant module thresholds (`module > 300 LOC`, `class > 250 LOC`, `> 3 service classes`) проверяются автоматически;
- service layer не импортирует transport DTO;
- cross-domain dependency разрешена только через facade/query/adapter boundary.

Эти проверки должны опираться на AST и package graph, а не только на regex по тексту.

Минимальный пример такой политики:

```python
# backend/tests/architecture/test_engine_purity.py
from pathlib import Path
import ast

FORBIDDEN_IMPORT_PREFIXES = {
    "sqlalchemy",
    "fastapi",
    "redis",
    "taskiq",
    "httpx",
}

def collect_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])

    return found

def test_engines_are_pure() -> None:
    for py in Path("backend/src/apps").rglob("engines/*.py"):
        imports = collect_imports(py)
        banned = sorted(imports & FORBIDDEN_IMPORT_PREFIXES)
        assert not banned, f"{py} has forbidden imports: {banned}"
```

Нужен не один тест, а набор policy tests:

- `test_engine_purity.py`
- `test_service_result_contracts.py`
- `test_service_constructor_dependencies.py`
- `test_service_module_thresholds.py`
- `test_transport_leakage.py`
- `test_cross_domain_boundaries.py`

Pipeline считается настроенным правильно только когда эти tests реально валят PR при нарушении стандарта.

## 17. Semantic invariants and deterministic behavior

Для analytical domains недостаточно зафиксировать только file/module shape.

Нужно зафиксировать предметные invariants:

- входные timestamps отсортированы и normalized;
- веса и probability-like coefficients проходят нормализацию и tolerance-check;
- `NaN`, `inf`, пустые окна и invalid boundary cases отсекаются до или внутри engine по явному правилу;
- одинаковый input + одинаковая config/version дают идентичный result;
- ranking order стабилен даже при равенстве score;
- threshold crossing всегда возвращает explainability reason.

Это должно подтверждаться tests двух типов:

- domain engine tests на invariants и deterministic branches;
- architecture policy tests на наличие required version/explainability fields в engine contracts, где это применимо.

## 18. Operational reliability policy

Для job-heavy и side-effect-heavy сервисов стандарт должен включать модель отказов, а не только структуру классов.

Обязательные правила:

- у re-runnable job/service операций есть explicit idempotency key policy;
- duplicate detection semantics задокументирована на уровне service contract;
- lock scope и lock ordering зафиксированы для конфликтующих write paths;
- exception taxonomy разделяет retryable и terminal failures;
- post-commit partial failure имеет явную стратегию: outbox, dedupe-safe dispatcher или compensating flow;
- safe re-run определяется явно для каждого background use case.

Примеры обязательных формулировок:

- `HistorySyncService.sync_batch(...)` обязан быть reentrant;
- повторный запуск с тем же `job_id` не создает дубликаты;
- side-effect dispatcher обязан быть dedupe-safe или работать через outbox boundary.

## 19. Performance budget policy

Service governance должен включать performance envelope, а не только code-shape rules.

Для heavy services и engines фиксируются:

- max query count per service operation;
- max batch size;
- p95/p99 target для sync path;
- memory ceiling для heavy analytical engine;
- правило, когда flow обязан уйти из sync path в job path.

Типовой стандарт:

- sync orchestration не делает неограниченный fan-out по queries;
- batch-heavy evaluation не исполняется inline, если превышен budget;
- suspicious large batch логируется и покрывается отдельным branch test.

Budgets должны жить рядом с contract/tests, а не только в устных договоренностях.

## 20. Explainability and reproducibility contract

Explainability должна быть частью typed result contract, а не “приятным бонусом в логах”.

Пример целевого explainability shape:

```python
@dataclass(frozen=True, slots=True)
class SignalFusionExplainability:
    dominant_factors: tuple[str, ...]
    threshold_crossings: tuple[str, ...]
    feature_scores: tuple[FeatureScore, ...]
    policy_path: str
```

Правила:

- engine возвращает result + explainability typed field, когда решение влияет на downstream automation;
- debug reasoning не размазывается по логам вместо контракта;
- `Clock` и `RandomSeed` передаются явно, если они участвуют в вычислении;
- `PolicyVersion`, `ModelVersion`, `WeightsVersion` входят в input/result contract, если влияют на outcome;
- golden-case tests доказывают, что одинаковые входы дают одинаковый output спустя месяцы.

## 21. Reference implementation: `signals`

Канонический reference module уже зафиксирован: `backend/src/apps/signals`.

Он переведен в final-form layout и закреплен ADR `[0009-signals-service-engine-split.md](../architecture/adr/0009-signals-service-engine-split.md)`:

- `services/` содержит orchestration-only services и explicit side-effect boundary;
- `engines/` содержит pure fusion/history analytical logic с typed contracts и explainability;
- `integrations/market_data.py` изолирует cross-domain data access;
- service tests покрывают wiring/invariants/post-commit behavior, а engine tests работают без DB/runtime wiring.

`signals` теперь не pilot промежуточной архитектуры, а реальный copyable template для остальных service/engine cutover-ов.

## 22. Architecture scorecard

Живой scorecard уже внедрен.

Источник истины:

- generator: `backend/scripts/export_service_layer_scorecard.py`
- policy model: `backend/tests/architecture/service_layer_scorecard.py`
- CI artifact: workflow `.github/workflows/architecture-governance.yml`, artifact `service-layer-scorecard`

Текущий generated snapshot:

| Domain | Service LOC / classes / files | Policy violations | Status | Plan |
| --- | --- | --- | --- | --- |
| `signals` | `917 / 2 / 6` | `clean` | `clean` | `Wave 1` |
| `patterns` | `2173 / 3 / 8` | `23 (cross_domain_boundaries=19, service_module_thresholds=3, service_result_contracts=1)` | `debt-open` | `Wave 2` |
| `anomalies` | `219 / 1 / 1` | `clean` | `clean` | `Wave 2` |
| `control_plane` | `719 / 3 / 7` | `clean` | `clean` | `Wave 2` |
| `cross_market` | `685 / 1 / 6` | `clean` | `clean` | `Wave 2` |
| `market_structure` | `1036 / 4 / 7` | `clean` | `clean` | `Wave 2` |
| `predictions` | `405 / 1 / 3` | `clean` | `clean` | `Wave 2` |
| `indicators` | `257 / 1 / 1` | `clean` | `clean` | `Wave 3` |
| `market_data` | `270 / 2 / 1` | `clean` | `clean` | `Wave 3` |
| `news` | `7 / 0 / 1` | `clean` | `clean` | `Wave 3` |
| `portfolio` | `194 / 1 / 1` | `clean` | `clean` | `Wave 3` |
| `hypothesis_engine` | `388 / 4 / 4` | `2 (service_result_contracts=1, transport_leakage=1)` | `debt-open` | `unplanned` |
| `system` | `4 / 0 / 1` | `clean` | `stable` | `unplanned` |

Итого:

- planned cutover domains из execution plan закрыты;
- автоматический scorecard теперь показывает не “ожидаемый план”, а фактический текущий debt surface;
- остаточные architectural violations локализованы и больше не требуют ручного аудита для обнаружения.

## 23. ADR package

ADR package уже добавлен.

Фактический состав:

- `[0010-caller-owns-commit-boundary.md](../architecture/adr/0010-caller-owns-commit-boundary.md)`
- `[0011-analytical-engines-never-fetch.md](../architecture/adr/0011-analytical-engines-never-fetch.md)`
- `[0012-services-return-domain-contracts.md](../architecture/adr/0012-services-return-domain-contracts.md)`
- `[0013-async-classes-for-orchestration-pure-functions-for-analysis.md](../architecture/adr/0013-async-classes-for-orchestration-pure-functions-for-analysis.md)`
- `[0014-post-commit-side-effects-only.md](../architecture/adr/0014-post-commit-side-effects-only.md)`

Package привязан к реальному governance surface:

- referenced from `backend/tests/architecture/service_layer_policy.py`;
- referenced from canonical `signals` service package;
- checked by `backend/tests/architecture/test_service_layer_adrs.py`.

ADR package не заменяет code/policy tests, но больше не является missing governance item.

## 24. Direct cutover priorities

План прямого cutover выполнен.

Реально исполненный порядок:

- guardrails first: architecture CI suite, scorecard generator, ADR package, runtime policy matrix и performance budgets добавлены до завершения governance block;
- Wave 1 complete: `signals` стал canonical service/engine reference module;
- Wave 2 complete: `market_structure`, `control_plane`, `cross_market`, `predictions`, `patterns/task_service_runtime`, `anomalies` переведены в final-form cutover;
- Wave 3 complete: `market_data`, `news`, `indicators`, `portfolio` переведены в final-form cutover.

Что важно:

- rewrite действительно шел как direct cutover, без промежуточных compatibility stages внутри service layer;
- planned hotspot scope execution plan закрыт полностью;
- remaining debt surface now lives outside этого executed plan и явно виден в generated scorecard, прежде всего в `patterns` и `hypothesis_engine`.

## 25. Definition of done

Service layer считается доведенным до целевого стандарта только если:

- active write/task orchestration идет через small class-based async services;
- analytical logic вынесена в explicit pure engine layer там, где она не является trivial;
- giant `services.py` cut into package where thresholds violated;
- service contracts typed;
- engine contracts typed;
- `dict[str, object]` result payloads removed from active service public methods;
- `{"status": ...}` payload semantics removed from active service public methods;
- services не принимают `AsyncSession` в constructors/public helpers;
- services не импортируют transport DTO;
- services no longer own HTTP concerns;
- services no longer own persistence internals beyond UoW/repository contracts;
- engines do not fetch or persist anything;
- services no longer own raw side-effect mechanics inline;
- cross-domain dependencies go only through explicit facade/query/adapter boundaries;
- semantic invariants, deterministic behavior, explainability and retry/reentrancy policy покрыты tests;
- architecture CI suite валит pipeline при нарушении правил;
- существует хотя бы один canonical reference module, который можно копировать;
- уже стандартизованные внешние контракты не были сломаны в ходе service rewrite;
- в service layer не осталось промежуточных compatibility stages.

На `2026-03-14` этот DoD достигнут для scope, зафиксированного в execution plan.

Открытый долг после выполнения плана не скрыт, а вынесен в явный post-plan surface:

- `patterns` остается основным локализованным hotspot по scorecard;
- `hypothesis_engine` сохраняет две policy violations и требует отдельного follow-up;
- planned cutover domains `signals`/`predictions`/`cross_market`/`control_plane`/`market_structure`/`patterns runtime`/`anomalies`/`market_data`/`news`/`indicators`/`portfolio` закрыты.

## 26. Главный вывод

Persistence и HTTP уже приведены к единому стандарту.

Service layer и analytical engine layer — последний слой, где проект еще может скатиться обратно в architectural blur, даже при чистых repositories и clean routers.

Этот план уже исполнен:

- правила превращены в CI-enforced policy;
- канонический reference module существует;
- planned hotspot domains переписаны в clean final form;
- governance artifacts больше не живут “когда-нибудь потом”, а зафиксированы в коде, CI и документации.

Следующий этап больше не общий service-layer rewrite, а точечная работа по остаточному debt surface, который теперь прозрачно виден в scorecard и не размазан по всей codebase.
