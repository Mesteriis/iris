# IRIS — Master Architecture Refactor Task
## Persistence Standardization + API Governance + HA Integration Contract

Ты работаешь внутри существующего проекта **IRIS**.

Твоя задача — провести **системный архитектурный рефакторинг** проекта, чтобы привести его к единому стандарту в двух больших областях:

1. **Persistence architecture**
2. **API architecture / governance**

Работать нужно **инкрементально, без слома текущего проекта**, с обязательной фиксацией изменений кодом, тестами, документацией и отдельными коммитами по этапам.

---

# Главная цель

Нужно перевести IRIS на архитектурно зрелую модель, в которой:

- работа с БД стандартизирована;
- direct DB access не размазан по коду;
- repository/query layer введён последовательно по всему проекту;
- raw SQL заменён на SQLAlchemy Core там, где это возможно;
- N+1 и скрытый lazy loading считаются дефектами;
- read path возвращает immutable typed objects;
- write path использует explicit mutable contract;
- транзакции управляются централизованно;
- все persistence operations хорошо логируются;
- API не является обязательным центром системы;
- сервис умеет работать как standalone и как Home Assistant addon;
- API разделено на независимые surfaces;
- есть probes;
- есть отдельный integration API для HA custom component;
- public API отдельный и защищён JWT;
- OpenAPI полная, версионируемая и контрактная;
- все endpoint-ы typed, tagged, versioned, documented;
- документация синхронна с кодом.

---

# Глобальные архитектурные принципы

Строго соблюдать:

- **async-first**
- **class-first**
- **SOLID**
- **Clean Architecture / DDD-lite**
- **event-driven friendly**
- **typed contracts**
- **incremental migration**
- **backward-compatible rollout**
- **no giant god-services**
- **no hidden architectural shortcuts**
- **docs must stay synchronized**
- **tests must be added immediately, not postponed**

---

# PART A — Persistence Architecture Standard

---

## A.1 Целевой persistence standard

Во всём проекте должен появиться единый и строгий слой доступа к данным.

Обязательные слои:

### 1. Repository layer
Используется для:
- write-side persistence;
- загрузки агрегатов / сущностей;
- controlled update flows;
- existence checks;
- delete/save/add operations.

### 2. Query services / read repositories
Используются для:
- сложных read-only запросов;
- detail/list views;
- dashboard/use-case reads;
- агрегированных и аналитических выборок;
- UI/API backing queries.

### 3. Unit of Work / transaction boundary
Нужен централизованный и понятный механизм:
- commit
- rollback
- flush
- transactional scope
- locking / `SELECT FOR UPDATE`

Repositories не должны произвольно владеть транзакционной политикой.

---

## A.2 Что считается нарушением и должно быть устранено

Нужно найти и устранить:

- direct `AsyncSession` usage outside persistence/composition layer;
- ORM queries inside routes/controllers;
- raw SQL strings in services/tasks/handlers;
- ad-hoc SQL in application logic;
- DB access from utils/helpers without clear infra role;
- repeated queries scattered across modules;
- random `commit()/rollback()/flush()` patterns;
- ORM objects leaking outside persistence layer;
- hidden lazy-loading outside repo/query layer;
- N+1 in list/detail flows;
- returning untyped `dict[str, Any]` where typed contracts should exist.

---

## A.3 ORM / SQLAlchemy Core / raw SQL policy

### Use ORM for:
- standard CRUD
- aggregate/entity loading
- relation loading
- regular domain persistence cases

### Use SQLAlchemy Core for:
- complex joins
- bulk operations
- upsert
- CTE
- window functions
- analytical queries
- performance-sensitive read paths
- cases where ORM becomes unclear or inefficient

### Raw SQL policy
Raw SQL is exception-only.

Raw SQL may remain only if:
- there is a real technical reason;
- SQLAlchemy Core would be materially worse;
- the reason is documented;
- the behavior is covered by tests;
- it is isolated inside infra/repository/query service layer.

Default rule:
**prefer SQLAlchemy Core / ORM abstractions, not raw SQL strings.**

---

## A.4 Anti-N+1 and loading policy

### N+1 is a defect
Treat N+1 and hidden lazy loading as architectural problems, not “optimization later”.

### Forbidden
- returning objects that can lazily hit DB outside persistence layer;
- relying on accidental lazy loading in services/API;
- fetching related data from layers above repo/query services.

### Required
- relation loading must be explicit;
- read model must be fully materialized before leaving persistence layer;
- caller must not depend on an open session;
- use eager loading or explicit projection intentionally;
- introduce loading profiles where useful.

Example loading profiles:
- `base`
- `with_relations`
- `full`

---

## A.5 Return type policy

### Default read contract
Read methods must return **typed immutable objects**, preferably:

- `@dataclass(frozen=True, slots=True)`

### Mutable objects
Mutable objects are allowed only through explicit write-oriented contracts, for example:
- `get_for_update(...)`
- `load_mutable(...)`

### Preferred contract style
Prefer explicit read/write separation:

- `get_read_by_id(...) -> FrozenReadModel | None`
- `get_for_update(...) -> MutableState | None`

Using a unified method like `get(..., frozen=True)` is allowed only if fully typed and clearly documented, but explicit read/write methods are preferred.

### Forbidden
- returning raw ORM objects outside persistence layer by default
- returning session-bound objects
- returning hidden-mutable read objects
- returning untyped dicts when typed contracts are practical

---

## A.6 Transaction policy

Must define and enforce a single transaction standard:

- repositories must not randomly call `commit()`;
- application service / UoW owns commit/rollback;
- `flush()` is allowed where technically necessary;
- locking scenarios must be explicit;
- transaction boundaries must be documented and predictable.

---

## A.7 Naming and responsibility rules

### Repository methods
Expected style:
- `add(...)`
- `get_by_id(...)`
- `get_read_by_id(...)`
- `get_for_update(...)`
- `save(...)`
- `delete(...)`
- `exists(...)`

### Query service methods
Expected style:
- `list_by_filter(...)`
- `fetch_page(...)`
- `find_matching(...)`
- `get_detail(...)`
- `get_stats(...)`
- `list_recent(...)`

### Avoid
- huge “do everything” methods
- mixing orchestration + mutation + formatting + analytics in one place
- business process methods inside repositories

---

## A.8 Logging / observability requirements for persistence layer

This is mandatory.

Implement a **unified structured logger** for persistence operations.

### DEBUG
Log:
- entry into repo/query methods;
- domain/entity name;
- operation name;
- loading profile;
- read/write mode;
- key filter parameters (without secrets);
- transaction events (`begin`, `flush`, `commit`, `rollback`);
- row counts where appropriate;
- bulk operation markers;
- fallback/exception persistence paths.

### INFO
Log:
- important state-changing operations;
- successful bulk changes;
- initialization of persistence components;
- migration path activation if relevant.

### WARNING
Log:
- suspiciously slow queries;
- fallback to raw SQL;
- legacy paths still present temporarily;
- potential N+1-prone usage if detected.

### ERROR / EXCEPTION
Log:
- DB access errors;
- mapping errors;
- transaction failures;
- lock timeouts;
- migration parity failures;
- Core/ORM replacement failures.

### Log requirements
- structured logging;
- no secret leakage;
- enough context to reconstruct operation history;
- consistent logger style across persistence layer.

---

## A.9 Required persistence migration workflow

### Stage A1 — audit current DB usage
Inspect the entire codebase and produce a map of:
- `AsyncSession` usage;
- `.execute(...)`;
- raw SQL / `text(...)`;
- ORM queries;
- `commit/flush/rollback`;
- direct DB access from routes/services/tasks/handlers;
- lazy-loading prone places;
- N+1-prone queries;
- ORM leakage outside infra;
- ambiguous read/write contracts.

Classify each case:
- `OK`
- `move to repository`
- `move to query service`
- `rewrite raw SQL to Core`
- `keep as justified raw SQL exception`
- `fix N+1/loading contract`
- `replace ORM leakage with typed model`
- `fix transaction boundary`

### Stage A2 — define persistence standard
Formalize:
- repository conventions;
- query service conventions;
- transaction policy;
- ORM/Core/raw SQL policy;
- read/write type policy;
- anti-N+1 policy;
- logging policy.

### Stage A3 — introduce repository layer
Create repositories by domain and migrate write-side access.

### Stage A4 — introduce query/read services
Create read-oriented query services and migrate read access.

### Stage A5 — migrate raw SQL to SQLAlchemy Core
Replace raw SQL where feasible, preserve behavior, document justified exceptions.

### Stage A6 — eliminate N+1 and enforce loading contracts
Fix critical query paths, add loading profiles where necessary.

### Stage A7 — enforce immutable read models and explicit mutable write models
Remove ORM leakage and standardize read/write object behavior.

### Stage A8 — standardize transaction boundaries
Centralize commit/rollback and clarify locking semantics.

### Stage A9 — add persistence logging/debug instrumentation
Instrument the whole persistence stack with unified structured logging.

### Stage A10 — cleanup and remove legacy access paths
Remove deprecated direct DB access and leave only documented exceptions.

---

## A.10 Persistence testing requirements

Write tests immediately at each stage.

Minimum required tests:
- repository unit tests;
- query service tests;
- behavior parity tests old vs new queries;
- SQLAlchemy Core replacement tests;
- transaction behavior;
- rollback behavior;
- lock/select-for-update flows;
- immutable read model behavior;
- mutable write model behavior;
- no session-bound object leakage;
- N+1 regression checks on critical paths;
- loading profile correctness;
- DB failure/error handling tests.

If replacing raw SQL, tests must prove:
- same result set;
- same filters;
- same ordering;
- same edge-case behavior;
- same business semantics.

---

# PART B — API Governance and Contract Standard

---

## B.1 Core API rule

**Core system must not depend on HTTP API.**

The following must work without API:
- runtime/event layers;
- persistence layer;
- schedulers/workers;
- application services;
- domain logic.

HTTP API is an **adapter**, not the application center.

---

## B.2 Deployment profiles

Support at least:

- `standalone`
- `ha-addon`
- `internal-only` if useful

---

## B.3 API surfaces

The service must support **multiple independent HTTP surfaces**, not a single monolithic API.

### 1. Probe surface
Operational endpoints:
- `GET /health`
- `GET /ready`
- `GET /live`
- `GET /version`
- optionally `GET /metrics`

Rules:
- may stay enabled even if all other APIs are disabled;
- are not business/public API;
- may remain unversioned;
- should still be documented when docs are enabled.

**Auth:** none

---

### 2. Home Assistant integration API
Dedicated API surface for the **custom Home Assistant component**.

Rules:
- separate surface and prefix;
- stable, minimal, versioned contract;
- dedicated DTOs;
- must not depend on public API being enabled;
- must not expose full internal/admin/public API;
- must be designed around HA use-cases, not internal architecture.

Example prefix:
- `/api/integration/v1/...`

**Auth:** none

Important:
This is a **trusted internal surface** and must not be publicly exposed by default.

---

### 3. Public API
Standalone/public API for external clients/UI.

Rules:
- optional;
- independently enableable;
- versioned;
- suitable for UI and external consumers.

Example prefix:
- `/api/public/v1/...`

**Auth:** JWT only

---

### 4. Admin / control API
Sensitive operational/control surface.

Examples:
- topology control
- config changes
- diagnostics
- replay/control operations
- admin actions

Rules:
- separately configurable;
- must not be mixed with integration/public;
- should be disabled by default in `ha-addon`;
- if enabled without auth, it must be strictly internal-only.

Example prefix:
- `/api/admin/v1/...`

**Auth:** none in current design, but only as internal-only surface

---

## B.4 API surface toggles / config

Support configuration by surface, not just `api.enabled`.

Example:

```yaml
service_mode: standalone | ha-addon | internal-only

api:
  probes:
    enabled: true

  integration:
    enabled: true
    prefix: /api/integration/v1

  public:
    enabled: false
    prefix: /api/public/v1

  admin:
    enabled: false
    prefix: /api/admin/v1

  docs:
    enabled: false

  metrics:
    enabled: true
```
B.5 Profile behavior
Standalone profile

probes enabled

integration API optional

public API configurable

admin API configurable

docs configurable

HA addon profile

probes enabled

integration API enabled

public API disabled by default

admin API disabled by default or internal-only

docs/openapi disabled by default

system must still work without public API

B.6 Auth / trust model

Strictly define:

Public API

JWT auth

Probe surface

no auth

HA integration API

no auth

Admin/control surface

no auth, but only as internal-only / non-public surface

Important deployment rule:
All auth-less surfaces must be protected by deployment boundary, not app-layer auth:

internal bind only

HA ingress/internal network

not published externally by default

B.7 API handler / Depends rules
Core rule

API endpoints must receive ready-to-use application services / query services / use-case handlers via dependency injection.

Endpoint handlers may:

validate input;

receive services through Depends(...);

call service methods;

map typed responses.

Endpoint handlers must not:

use AsyncSession directly as working tool;

execute DB queries directly;

manually instantiate repositories;

manually instantiate services;

manually manage transactions;

contain business orchestration.

Composition rule

Dependencies such as:

session

repositories

unit of work

query services

logger

config

must be assembled in DI/composition layer, not inside route handlers.

B.8 API contract rule

Every non-probe endpoint must be treated as a versioned, documented contract.

No endpoint should exist without:

versioned path;

tag;

summary;

description;

typed request schema;

typed response schema;

documented error responses;

stable operationId.

B.9 Versioning policy
Required

All non-probe APIs must be versioned.

Examples:

/api/integration/v1/...

/api/public/v1/...

/api/admin/v1/...

Rules

versioning strategy must be documented;

breaking changes require a new version;

deprecated endpoints must be marked;

changelog must reflect API contract changes;

future coexistence of versions should remain possible where practical.

Probe endpoints may remain unversioned.

B.10 OpenAPI requirements

OpenAPI is mandatory and is part of the contract.

For every endpoint explicitly document:

summary

description

tags

request model

response model

error responses

auth requirements

operationId

versioned path

Tags

Use meaningful tags at minimum:

probes

integration

public

admin

topology

signals

decisions

portfolio

system

metrics

Docs configurability

docs/openapi may be disabled in ha-addon by default;

docs may be enabled in standalone mode;

disabling docs must not remove typed contracts from code;

schema generation must remain valid whenever docs are enabled.

B.11 Error contract standard

Introduce a unified error envelope.

Error shape

At minimum:

code

message

details

request_id

trace_id

timestamp

Error categories that must be documented

Minimum:

validation error

bad request

unauthorized

forbidden

not found

conflict

unprocessable entity

rate limited

internal server error

service unavailable / dependency failure

Use reusable OpenAPI components for common errors.

B.12 Request tracing / context

All API surfaces must support request tracing.

Minimum context:

request_id

trace_id

correlation_id where applicable

service_mode

api_surface

Requirements:

these identifiers must be logged;

should appear in error responses where appropriate;

should propagate into application layer where useful.

B.13 Response model policy

all endpoints must return typed response models;

no loose dict responses;

no ORM models in API contracts;

no direct exposure of internal persistence/domain models;

integration API must use dedicated DTOs;

admin API must use dedicated DTOs;

public API must use dedicated DTOs.

B.14 Pagination / filtering / sorting standard

Define a shared contract for list endpoints.

Must standardize:

pagination style;

filter naming;

sorting syntax;

list response metadata.

Use consistent patterns for:

limit

offset or cursor

sort

filter params

response meta

B.15 Date/time contract

all datetimes must be timezone-aware;

use UTC by default;

use ISO 8601 in API contracts;

no naive/local datetime values in external contracts.

B.16 Idempotency / command policy

For write/control endpoints define:

which operations are idempotent;

repeated-call semantics;

whether idempotency key is needed for dangerous commands;

clear behavior for apply/refresh/control actions.

B.17 Timeout / async work policy

HTTP endpoints must not perform heavy long-running work inline unless clearly justified.

Preferred pattern:

accept command;

enqueue/background trigger/event;

return acknowledgement / status / job id / 202 Accepted if appropriate.

Especially relevant for:

resync

recalculation

topology apply

batch commands

expensive integrations

B.18 Capability discovery

Provide a capability/status endpoint for clients such as HA custom component.

Example:

/api/integration/v1/capabilities

Expose:

enabled surfaces;

service mode;

available features;

API version;

supported integration capabilities.

B.19 API modularity

API must be mounted by modules/surfaces, e.g.:

probes router

integration router

public router

admin router

metrics router

Mount conditionally by config/profile.

B.20 API logging and audit requirements
Structured request logging

Log:

request start/end;

route name;

api surface;

status code;

request_id/trace_id;

duration;

application errors;

unexpected exceptions.

Audit logging

For write/control/admin operations log:

who/what called;

which endpoint;

what changed;

old/new values where relevant;

result status.

Even for auth-less internal surfaces, capture technical context.

B.21 Forbidden API patterns

Do not allow:

direct DB access in routes/controllers;

direct AsyncSession usage in routes/controllers;

raw SQL in routes/controllers;

business orchestration inside handlers;

exposing full internal API to HA integration;

making core features accessible only through HTTP;

leaking ORM/internal models via API;

undocumented endpoints;

unversioned business APIs;

endpoints without tags / errors / response models.

B.22 API testing requirements

Tests must cover:

Surface/profile behavior

standalone profile

ha-addon profile

public disabled

admin disabled

integration enabled

probes enabled

Contract tests

OpenAPI schema builds

versioned prefixes are respected

tags exist

response models exist

documented errors exist

Auth tests

JWT required on public API

no auth on probes

no auth on integration API

no auth on internal admin surface when configured internal-only

surface exposure follows config/profile

DI tests

handlers use service dependencies

no direct DB access in handlers

no business logic in controllers

Response/error tests

typed success responses

typed error envelope

request_id/trace_id propagation

validation and domain errors mapped consistently

PART C — Delivery, commits, docs, migration process
C.1 General delivery rule

Work incrementally.

After each stage:

create a separate commit;

run tests immediately;

update README if affected;

update architecture docs if affected;

update CHANGELOG if affected.

Do not accumulate everything into one giant commit.

C.2 Suggested stages
Stage 1 — full architecture audit

inspect persistence usage

inspect API structure

inspect current contracts

inspect current deployment/profile behavior

produce migration map

Stage 2 — persistence standard design

repository/query/UoW conventions

ORM/Core/raw SQL policy

return type policy

anti-N+1 policy

logging policy

Stage 3 — repository layer rollout

introduce repositories

migrate write-side access

Stage 4 — query service rollout

migrate read-side access

introduce immutable read models

Stage 5 — raw SQL migration

replace with SQLAlchemy Core where feasible

document justified exceptions

Stage 6 — N+1 elimination and loading contract enforcement

fix critical query paths

add loading profiles

Stage 7 — transaction standardization

centralize commit/rollback

clarify locking/UoW behavior

Stage 8 — persistence logging/debug instrumentation

structured logging across persistence stack

Stage 9 — API surface refactor

modular routers

profile-aware mounting

integration/public/admin/probes split

Stage 10 — API contract hardening

typed DTOs

versioned paths

tags

error envelope

OpenAPI completion

Stage 11 — DI cleanup

ensure handlers depend on ready-made services

remove direct DB access from API layer

Stage 12 — tests + docs sync + cleanup

remove legacy paths

sync README/architecture/changelog

finalize migration notes

C.3 Commit discipline

Use clear commit messages, for example:

refactor(persistence): audit database access points

feat(persistence): add repository layer conventions

feat(persistence): add read query services

refactor(persistence): migrate raw sql to sqlalchemy core

fix(persistence): eliminate n-plus-one in critical queries

feat(persistence): introduce immutable read models

refactor(persistence): standardize transaction boundaries

feat(logging): add structured logging for persistence and api

refactor(api): split surfaces into probes integration public admin

feat(api): add versioned contracts and openapi metadata

docs(architecture): sync readme architecture and changelog

C.4 Documentation requirements

Keep synchronized:

README.md

architecture docs

CHANGELOG.md

OpenAPI schema

Must document:

persistence rules

repository/query service rules

ORM/Core/raw SQL policy

anti-N+1 policy

immutable/mutable read/write policy

transaction policy

persistence logging policy

API surfaces

deployment profiles

auth model

versioning policy

deprecation policy

integration API for HA custom component

probes semantics

error envelope

DI rules for API

Docs must be updated as changes are introduced, not only at the end.

Expected final result

IRIS must end with:

Persistence side

unified repository/query persistence standard

isolated DB access layer

minimal direct session usage outside infra

raw SQL migration to SQLAlchemy Core where feasible

documented raw SQL exceptions where unavoidable

anti-N+1 loading contracts

immutable read models by default

explicit mutable write models

centralized transaction boundaries

structured debug/error logging for persistence operations

tests proving parity and correctness

API side

optional/modular API architecture

probes surface

dedicated HA integration API

optional public API

optional/internal admin API

JWT only on public API

no auth on probes/integration/internal-only surfaces

full OpenAPI coverage

versioned contracts

tags

documented error responses

typed DTOs

DI-based endpoint composition

stable HA custom component contract

tests proving profile/surface correctness

Project hygiene

separate commits by stage

immediate tests

synced README / architecture docs / CHANGELOG

no stale architecture docs after refactor