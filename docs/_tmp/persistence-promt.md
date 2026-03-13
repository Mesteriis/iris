# IRIS — Unified Persistence Refactor Task
## Repository Layer + SQLAlchemy Core Migration + Immutable Read Models + Anti-N+1 + Debug Logging

Ты работаешь внутри существующего проекта **IRIS**.

Твоя задача — **внедрить единый стандарт persistence-архитектуры во весь проект**, не ломая текущую бизнес-логику, и последовательно перевести проект на:

- repository layer;
- query/read services;
- controlled transaction boundaries;
- typed immutable read models;
- explicit mutable write models;
- SQLAlchemy Core вместо raw SQL там, где это возможно и оправдано;
- anti-N+1 loading policy;
- расширенный debug/error logging для всех операций доступа к данным.

---

# Главная цель

В проекте должен появиться **единый и строгий слой работы с БД**, где:

- доступ к БД перестаёт быть размазан по routes/services/tasks/handlers;
- бизнес-логика не строит ad-hoc SQL;
- чтение и запись идут через `Repository` / `QueryService`;
- raw SQL либо переписан на SQLAlchemy Core, либо оставлен как редкое и документированное исключение;
- read path по умолчанию возвращает **immutable typed objects**;
- write path использует **явный mutable contract**;
- скрытые lazy-loading / N+1 считаются дефектом;
- транзакции и commit/rollback управляются централизованно;
- все DB-операции, ошибки, транзакции и repo-вызовы хорошо логируются.

---

# Обязательные архитектурные принципы

Следовать строго:

- **async-first**
- **class-first**
- **SOLID**
- **Clean Architecture / DDD-lite**
- **typed contracts**
- **incremental migration**
- **backward-compatible rollout**
- **no giant god-services**
- **no direct DB access from API/application surface**
- **no accidental lazy loading**
- **no ORM leakage outside persistence layer by default**
- **no random commit/rollback spread across codebase**

---

# Обязательный целевой стандарт

## Persistence layers
В проекте должны быть чётко выделены:

### 1. Repository layer
Для write-side и domain-oriented persistence:
- загрузка агрегатов / сущностей;
- сохранение;
- удаление;
- existence checks;
- controlled update paths.

### 2. Query services / read repositories
Для:
- сложных read-only выборок;
- списков;
- аналитических таблиц;
- detail/list API responses;
- dashboard/read-model use-cases.

### 3. Unit of Work / transaction boundary
Должен быть единый и понятный механизм:
- commit;
- rollback;
- flush;
- transactional scope.

Repositories не должны произвольно коммитить транзакции без согласованной политики.

---

# Что считается проблемой и подлежит исправлению

Нужно найти и исправить такие нарушения:

- direct `AsyncSession` usage outside persistence layer;
- ORM queries inside routes/controllers;
- raw SQL strings in services/tasks/handlers;
- ad-hoc SQL в application logic;
- DB access в utils/helpers без явной инфраструктурной роли;
- повторяющиеся запросы в нескольких местах;
- хаотичный commit/rollback;
- ORM objects leaking into API/application layers;
- lazy loading outside repo/query layer;
- N+1 in list/detail flows;
- возврат untyped `dict[str, Any]` там, где можно вернуть typed contract.

---

# Политика ORM / SQLAlchemy Core / raw SQL

## Использовать ORM для:
- стандартного CRUD;
- загрузки агрегатов;
- relation loading;
- обычных domain persistence cases.

## Использовать SQLAlchemy Core для:
- сложных joins;
- bulk operations;
- upsert;
- CTE;
- window functions;
- аналитических выборок;
- performance-sensitive reads;
- случаев, где ORM делает код хуже или менее явным.

## Raw SQL допустим только как исключение
Оставлять raw SQL можно только если одновременно:
- есть реальная техническая причина;
- SQLAlchemy Core не даёт адекватного решения или делает код существенно хуже;
- причина явно задокументирована;
- поведение покрыто тестами;
- это изолировано в infrastructure-level adapter/repository method.

По умолчанию: **не raw SQL, а SQLAlchemy Core / ORM abstractions**.

---

# Политика anti-N+1 и загрузки связей

## N+1 считать дефектом
Это не “оптимизация потом”, а архитектурная ошибка.

## Запрещено
- возвращать объекты, которые потом внезапно идут в БД через lazy relation;
- полагаться на случайный lazy loading в API/services;
- тянуть связанные данные из слоя выше repo/query service.

## Обязательно
- все relation loading strategies должны быть явными;
- read model к моменту возврата должна быть уже полностью сформирована;
- caller не должен зависеть от открытой session;
- для сложных read flows использовать explicit projection или Core;
- поддержать loading profiles там, где это уместно.

Пример:
- `base`
- `with_relations`
- `full`

---

# Политика возвращаемых типов

## По умолчанию
Read methods должны возвращать **typed immutable objects**, предпочтительно:

- `@dataclass(frozen=True, slots=True)`

ORM models не должны быть дефолтным результатом repo/query методов вне persistence layer.

## Mutable objects
Mutable объекты допускаются **только по явному write-контракту**, например:
- `get_for_update(...)`
- `load_mutable(...)`

Они должны использоваться только в write/use-case сценариях.

## Предпочтительный контракт
Разделяй read и write явно.

Хорошо:
- `get_read_by_id(...) -> FrozenReadModel | None`
- `get_for_update(...) -> MutableState | None`

Допустимо, если строго типизировано и задокументировано:
- `get(..., frozen=True)`

Но предпочтение — отдельным методам для read/write path.

## Запрещено
- возвращать наружу сырой ORM object по умолчанию;
- возвращать `dict[str, Any]`, если можно сделать typed dataclass;
- возвращать объекты, зависящие от открытой session;
- возвращать сущности со скрытой мутабельностью, если это read path.

---

# Политика transaction boundary

Нужно ввести единый стандарт:

- repositories не должны randomly `commit()`;
- application service / UoW владеет commit/rollback;
- `flush()` допустим внутри repo, если это технически нужно;
- `get_for_update()` и locking-сценарии должны быть явными;
- transaction boundary должна быть понятной и документированной.

---

# Политика именования и контрактов

## Repository methods
Ожидаемые методы:
- `add(...)`
- `get_by_id(...)`
- `get_read_by_id(...)`
- `get_for_update(...)`
- `save(...)`
- `delete(...)`
- `exists(...)`

## Query service methods
Ожидаемые методы:
- `list_by_filter(...)`
- `fetch_page(...)`
- `find_matching(...)`
- `get_detail(...)`
- `get_stats(...)`
- `list_recent(...)`

## Нежелательно
- методы типа `process_and_update_everything()`
- методы, одновременно делающие orchestration, mutation, analytics и formatting
- смешение read/write/transport responsibilities в одном методе

---

# Logging / observability requirements

Это обязательная часть задачи.

Нужно внедрить **единый логгер для persistence-слоя**, который покрывает:

- repo operations;
- query service operations;
- DB reads/writes;
- transaction start/commit/rollback;
- flush;
- lock/select-for-update;
- cacheable expensive reads;
- raw SQL exceptions;
- SQLAlchemy Core query execution points;
- error paths.

## Уровни логирования
Минимально:

### DEBUG
Логировать:
- вход в repo/query method;
- название операции;
- сущность/домен;
- ключевые параметры поиска (без утечки секретов);
- loading profile;
- выбранный режим (`read` / `write`);
- транзакционные события (`begin`, `flush`, `commit`, `rollback`);
- количество найденных записей;
- признаки bulk operation;
- fallback/exceptional persistence paths.

### INFO
Логировать:
- важные state-changing операции;
- успешные bulk changes;
- миграции поведения;
- переключение на fallback path;
- инициализацию persistence components.

### WARNING
Логировать:
- suspicious slow query cases;
- fallback на raw SQL;
- потенциальные N+1-prone места;
- deprecated persistence paths, если временно оставляются.

### ERROR / EXCEPTION
Логировать:
- ошибки DB access;
- mapping errors;
- transaction failures;
- lock timeouts;
- unexpected empty results в критичных write-path операциях;
- migration parity failures;
- failures при замене raw SQL на Core/ORM equivalents.

## Требования к логам
- логирование должно быть структурированным;
- не логировать секреты;
- не логировать избыточные payload целиком без необходимости;
- лог-сообщения должны помогать восстанавливать историю операций;
- логгер должен быть единообразным по всему persistence-слою.

---

# Этап 1. Аудит текущего проекта

Сначала нужно полностью изучить проект и составить **карту текущего persistence usage**.

## Найти:
- все места использования `AsyncSession`;
- все `.execute(...)`;
- все raw SQL / `text(...)`;
- все ORM queries;
- все `commit/flush/rollback`;
- все direct DB access из routes/services/tasks/handlers;
- все lazy-loading prone места;
- все потенциальные N+1;
- все возвраты ORM objects за пределы infra;
- все места, где read/write контракты неочевидны.

## Классифицировать каждую точку:
- `OK`
- `move to repository`
- `move to query service`
- `rewrite raw SQL to Core`
- `keep as justified raw SQL exception`
- `fix N+1/loading contract`
- `replace ORM leakage with typed model`
- `fix transaction boundary`

## Результат этапа
Подготовить:
- audit report;
- список файлов и проблем;
- migration plan по доменам;
- список current behavior to preserve.

После этапа обязательно:
- commit
- tests if touched
- update docs if needed

---

# Этап 2. Проектирование persistence standard

Нужно formalize и внедрить:

- repository interfaces/conventions;
- query service conventions;
- read/write object policy;
- transaction policy;
- ORM vs Core policy;
- raw SQL exception policy;
- anti-N+1 loading policy;
- logging policy.

## Результат этапа
- единый persistence design doc;
- agreed code structure;
- naming conventions;
- migration rules.

После этапа обязательно:
- commit
- tests if touched
- update README / architecture / changelog

---

# Этап 3. Внедрение repository layer

По доменам ввести repository layer.

Для каждого relevant domain:
- создать repository interfaces/implementations;
- перенести туда write-oriented DB access;
- изолировать persistence logic;
- убрать direct DB access из caller layers.

Repositories должны быть:
- async;
- class-based;
- typed;
- логируемыми;
- с понятной ответственностью.

После этапа обязательно:
- commit
- tests
- docs update

---

# Этап 4. Внедрение query/read services

Для сложных read-сценариев:
- выделить query services / read repositories;
- перенести туда сложные выборки;
- заменить ad-hoc queries из сервисов/роутов;
- вернуть immutable typed read models.

Read path должен:
- не использовать скрытый lazy loading;
- не зависеть от open session;
- быть безопасным по mutability semantics.

После этапа обязательно:
- commit
- tests
- docs update

---

# Этап 5. Перенос raw SQL на SQLAlchemy Core

Найти все raw SQL и для каждого:

1. понять, зачем он нужен;
2. попытаться переписать на SQLAlchemy Core;
3. если нецелесообразно — оставить как exception и задокументировать.

Нужно:
- использовать Core expressions для сложных query paths;
- сохранить поведение;
- покрыть тестами эквивалентность.

После этапа обязательно:
- commit
- tests
- update changelog/docs

---

# Этап 6. Устранение N+1 и фиксация loading contracts

Нужно:
- найти N+1-prone запросы;
- ввести explicit eager loading / explicit projection;
- ввести loading profiles, где нужно;
- запретить repo/query methods возвращать lazy-dependent objects.

Проверить критичные:
- list endpoints;
- detail endpoints;
- dashboard queries;
- orchestration paths;
- background jobs with loops over entities.

После этапа обязательно:
- commit
- tests
- docs update

---

# Этап 7. Внедрение immutable read models / mutable write models

Нужно:
- перевести read методы на `@dataclass(frozen=True, slots=True)` или эквивалент;
- выделить mutable state objects только для write scenarios;
- убрать утечку ORM-моделей за пределы persistence layer;
- сделать read/write contracts явными.

Предпочтительный стандарт:
- `get_read_by_id(...)`
- `get_for_update(...)`

Если используется единый getter — mutability semantics должны быть явно типизированы и задокументированы.

После этапа обязательно:
- commit
- tests
- docs update

---

# Этап 8. Транзакционная стандартизация

Нужно:
- централизовать commit/rollback policy;
- убрать случайные transaction boundaries;
- ввести/доработать Unit of Work или equivalent mechanism;
- сделать locking operations явными.

После этапа обязательно:
- commit
- tests
- docs update

---

# Этап 9. Logging and debug instrumentation

Нужно внедрить единый structured logger во весь persistence stack.

Ожидается:
- debug logs на repo/query operations;
- transaction lifecycle logs;
- error logs with enough context;
- logging wrappers/adapters where appropriate;
- единый стиль логирования.

Важно:
- логи не должны раскрывать секреты;
- логи должны помогать воспроизводить историю операций;
- debug logging должен быть полезен для расследования ошибок и сложных сценариев.

После этапа обязательно:
- commit
- tests
- docs update / changelog

---

# Этап 10. Очистка и финальная миграция callers

Нужно:
- перевести routes/controllers/services/tasks/handlers на repo/query usage;
- удалить старые direct DB access paths;
- оставить только задокументированные исключения;
- убедиться, что новая модель стала стандартом проекта.

После этапа обязательно:
- commit
- tests
- update README / architecture / changelog

---

# Обязательные требования к тестам

Тесты писать **сразу после каждого этапа**, не откладывать.

Минимально нужны тесты на:

- repository methods;
- query services;
- behavior parity старого и нового запроса;
- SQLAlchemy Core replacements;
- transaction behavior;
- rollback behavior;
- lock/select-for-update flows;
- immutable read model behavior;
- mutable write model behavior;
- no session-bound object leakage;
- N+1 regression checks on critical paths;
- loading profile correctness;
- logging hooks where practical;
- error handling on DB failures.

Если старый raw SQL заменяется Core-эквивалентом — тестами доказать:
- тот же результат;
- те же фильтры;
- та же сортировка;
- те же edge cases;
- та же бизнес-семантика.

---

# Обязательные требования к коммитам

После **каждого этапа**:
- отдельный commit;
- тесты прогнаны;
- документация обновлена, если менялась архитектура/контракты/поведение.

Предпочтительные commit messages:
- `refactor(persistence): audit database access points`
- `feat(persistence): add repository layer conventions`
- `feat(persistence): add query services for read paths`
- `refactor(persistence): migrate raw sql to sqlalchemy core`
- `fix(persistence): eliminate n-plus-one in critical queries`
- `feat(persistence): introduce immutable read models`
- `refactor(persistence): standardize transaction boundaries`
- `feat(logging): add structured debug logging for persistence layer`
- `docs(persistence): sync readme architecture and changelog`

---

# Обязательные требования к документации

Нужно поддерживать в актуальном состоянии:

- `README.md`
- архитектурную документацию
- `CHANGELOG.md`

Обязательно зафиксировать:
- где в проекте можно работать с БД;
- где нельзя;
- когда использовать repository;
- когда использовать query service;
- когда использовать ORM;
- когда использовать SQLAlchemy Core;
- когда допустим raw SQL;
- как работает anti-N+1 policy;
- как работает immutable/mutable contract;
- как работает transaction policy;
- как работает persistence logging.

Документация должна обновляться **по ходу внедрения**, а не только в конце.

---

# Что запрещено делать

- делать giant repository на весь проект;
- оставлять старые DB access paths параллельно новым без миграции;
- выпускать ORM models наружу по умолчанию;
- оставлять lazy loading как часть public contract;
- прятать commit/rollback в случайных местах;
- заменять raw SQL на ещё более запутанный слой;
- жертвовать типизацией ради скорости;
- откладывать тесты “на потом”;
- откладывать README/architecture/changelog “на потом”.

---

# Что ожидается в финале

В результате проект должен получить:

- единый repository/query persistence standard;
- изолированный DB access layer;
- минимизацию direct session usage вне infra;
- raw SQL migration to SQLAlchemy Core where feasible;
- documented exceptions for unavoidable raw SQL;
- anti-N+1 loading contracts;
- immutable read models by default;
- explicit mutable write models;
- centralized transaction boundaries;
- structured debug/error logging for persistence operations;
- tests, proving parity and correctness;
- synced README / architecture docs / changelog.

---

# Формат работы агента

Работай как **senior architect + senior backend engineer**.

На каждом этапе:
1. сначала изучи, что уже есть;
2. не ломай рабочее поведение без причины;
3. переиспользуй существующие подходящие абстракции;
4. не создавай параллельную архитектуру без необходимости;
5. объясняй trade-offs;
6. фиксируй изменения кодом, тестами, документацией и коммитом.

Главное:
**нужно не просто "добавить repo слой", а перевести IRIS на управляемую, типизированную, наблюдаемую и безопасную persistence-модель.**