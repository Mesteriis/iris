# IRIS Backend Business Localization Plan

## Цель

Зафиксировать, как IRIS должен поддерживать мультиязычность на backend-уровне так, чтобы:

- пользователь понимал business narration в API, Home Assistant, event-like delivery surfaces и operation status flows;
- machine contracts оставались каноническими и пригодными для automation;
- уже принятые `service/engine` и presenter boundaries не ломались;
- localization встроилась в существующую governance-модель репозитория, а не жила отдельной “mini-architecture”.

Этот документ описывает именно **backend business localization**, а не frontend i18n.

## Архитектурный контекст

План должен работать внутри уже принятых ограничений IRIS:

- service layer и analytical engines уже разделены;
- post-commit side effects уже вынесены отдельно;
- runtime event-driven и управляется control plane;
- HTTP API живет под OpenAPI/capability governance и analytical cache rules;
- Home Assistant является внешним automation/notification host;
- AI-layer является отдельной capability и не должен подменять deterministic localization.

Связанные документы:

- `docs/iso/service-layer-refactor-audit.md`
- `docs/architecture/service-layer-runtime-policies.md`
- `docs/architecture/service-layer-performance-budgets.md`
- `docs/architecture/adr/0003-control-plane-event-routing.md`
- `docs/architecture/adr/0008-research-vs-production-runtime.md`
- `docs/iso/lazy-investor-ai-plan.md`

## Текущее состояние репозитория

На момент этого плана есть несколько конкретных ограничений, которые надо учитывать, а не обходить абстракциями:

- `apps/signals/read_models.py` и `apps/signals/schemas.py` все еще живут на `reason: str`, а не на formalized `reason_code`;
- `apps/signals/api/contracts.py` и `apps/portfolio/api/contracts.py` пока просто переэкспортируют `schemas.py`, то есть API boundary еще недостаточно отделен от app-level contract layer;
- `core/http/cache.py` сейчас использует `Vary: Accept, If-None-Match` и не учитывает язык;
- в `core/settings/base.py` есть только одиночное поле `language`, без полноценной locale policy;
- `runtime/streams/messages.py` все еще живет в text-first модели `AnalysisMessage(topic, text, ...)`;
- `ha/integration/custom_components/iris/coordinator.py` прокидывает raw `reason` в события `iris.decision` и `iris.investment_signal`;
- HA integration пока не имеет `strings.json` / `translations`, а `sensor.py` hardcodes `_attr_name = "status"`.

Из этого следует: localization нельзя начинать с “переводов строк”. Сначала нужен canonical taxonomy и transport-safe foundation.

## Проблема

Сейчас backend mostly возвращает machine-oriented semantics:

- canonical event types;
- decision/status values;
- reason-like raw strings;
- operation messages как свободный текст;
- HA payloads и legacy bus messages без formalized descriptor model.

Для automation это правильно, но для человека этого недостаточно:

- пользователь видит system vocabulary вместо понятного сообщения;
- reason/text поля уже сейчас неформализованы и плохо переводимы;
- язык вывода не контролируется ни в API cache semantics, ни в HA delivery;
- перевод и business truth легко начинают смешиваться внутри boundary code.

## Scope

Этот документ покрывает только backend-owned human-facing text:

- human-readable business messages в API responses;
- HA-facing business narration;
- event/SSE/push payloads, которые предназначены не только для машин;
- operation status narration;
- persisted notifications или similar artifacts, если они принадлежат backend;
- deterministic summaries и briefs, если они не AI-generated.

Этот документ не покрывает:

- frontend UI translations;
- перевод произвольного пользовательского контента из БД;
- AI-generated freeform translation как primary mechanism;
- перевод machine identifiers вроде `BUY`, `SELL`, `signal_created`, `market_regime_changed`.

## Основная идея

Переводится не сама бизнес-логика.

Переводится то, **что система говорит человеку о результатах этой логики**.

Правильная модель для IRIS:

- machine outcome остается canonical;
- поверх него появляется formalized narration descriptor;
- descriptor рендерится на boundary в нужной локали;
- человек получает понятный текст, а automation продолжает жить на codes.

## Non-Negotiable правила

### 1. Canonical taxonomy first

Localization не начинается с текста. Она начинается с formalized machine vocabulary.

Минимальный canonical набор:

- `decision`
- `status`
- `reason_code`
- `severity_code`
- `action_code`
- typed numeric / temporal / symbolic facts

Пока домен живет на `reason: str`, переводить его напрямую нельзя.

### 2. Machine contracts остаются источником истины

Automation, routing, policies, alerts и downstream integrations обязаны опираться на canonical fields, а не на localized text.

### 3. Локализация не живет в engines

Pure engines и deterministic domain math не должны:

- принимать locale;
- ходить в translation catalog;
- рендерить human text;
- форматировать labels/percentages/durations.

### 4. Локализация не живет в orchestration services как inline strings

Service может вернуть codes/facts/result contract, но не должен превращаться в разрозненный string-builder.

### 5. Boundary contracts отделяются от app schemas

Нельзя просто добавлять `message_key/message/message_params` в текущие app-level `schemas.py`, если эти же схемы переиспользуются как доменная форма.

Localization должен приходить через отдельные API/HA envelopes и presenter contracts.

### 6. Одна narration system на поверхность

Нельзя оставлять parallel world:

- новый descriptor-based API/HA layer;
- старый text-first `AnalysisMessage.text`;
- отдельные ad-hoc operation messages.

Для каждой поверхности должен быть один целевой narration model и понятный deprecation path для legacy текста.

### 7. AI не является primary translation mechanism

AI может расширять explanation или humanize deterministic outcome, но не подменяет canonical descriptor layer.

## Migration matrix для legacy полей

Это надо зафиксировать явно, иначе rollout станет вязким.

| Текущее поле | Целевая форма | Переходное состояние |
| --- | --- | --- |
| `reason: str` | `reason_code` | `reason` временно остается как deprecated legacy text |
| `message: str` | `message_key` + `message_params` + optional rendered `message` | допустим transitional dual-field contract на pilot surfaces |
| `status: str` | `status` | остается canonical |
| `decision: str` | `decision` | остается canonical |
| `text` в legacy bus | descriptor или explicit deprecated text field | legacy bus включается в отдельную cleanup wave |

## Целевая модель контракта

### 1. Machine outcome

Это typed result / read model / event payload без локализации.

Пример:

```json
{
  "decision": "BUY",
  "confidence": 0.82,
  "reason_code": "signals.regime_alignment.high",
  "symbol": "BTC",
  "timeframe_minutes": 60
}
```

### 2. Message descriptor

Поверх machine outcome строится deterministic narration descriptor:

```python
@dataclass(frozen=True, slots=True)
class MessageDescriptor:
    key: str
    params: Mapping[str, object]
    surface: str
    variant: str | None = None
    audience: str | None = None
    severity_code: str | None = None
```

`surface` нужен сразу, чтобы не перегружать один и тот же message key под разные выходы:

- `api_read`
- `ha_event`
- `ha_notification`
- `operator_status`

`variant` нужен для короткой/обычной/расширенной формы:

- `short`
- `default`
- `detailed`

### 3. Localized render

Boundary adapter затем рендерит локализованную форму:

```python
@dataclass(frozen=True, slots=True)
class LocalizedMessage:
    key: str
    locale: str
    text: str
    params: Mapping[str, object]
```

### 4. Финальный user-facing payload

```json
{
  "decision": "BUY",
  "confidence": 0.82,
  "reason_code": "signals.regime_alignment.high",
  "message_key": "signals.decision.buy.regime_alignment_high",
  "message_params": {
    "symbol": "BTC",
    "timeframe_minutes": 60,
    "confidence": 0.82
  },
  "message": {
    "locale": "ru",
    "text": "BTC показывает сильное бычье подтверждение на часовом таймфрейме."
  }
}
```

Важно: `message_params` содержат только семантику, а не заранее formatted labels вроде `timeframe_label: "1h"` или `confidence_pct: 82`.

## Целевая layer model

### 1. `core/i18n`

Нужен общий backend localization core:

```text
src/core/i18n/
  contracts.py
  locale.py
  resolver.py
  translator.py
  formatting.py
  catalogs/
    en.py
    ru.py
    es.py
    uk.py
```

Роль:

- определить supported locales;
- выбрать effective locale;
- рендерить `message_key + params -> text`;
- форматировать числа, проценты, signed deltas, counts, dates, durations;
- обеспечивать fallback policy.

### 2. Domain narratives

В доменах, где нужен human-readable backend output, должен быть pure narration layer:

```text
src/apps/signals/narratives/
src/apps/portfolio/narratives/
src/apps/anomalies/narratives/
src/apps/market_structure/narratives/
```

Роль:

- принимать typed domain result или read model;
- возвращать `MessageDescriptor`;
- не делать IO;
- не знать ничего о HTTP, HA, Redis Streams или AI providers.

### 3. Boundary adapters

Localization render должен жить в presenters/adapters:

- API presenters;
- HA bridge adapters;
- notification presenters;
- SSE / event presenters.

Именно они:

- берут `MessageDescriptor`;
- выбирают locale;
- вызывают translator;
- добавляют rendered text в response/event.

### 4. API-localized contracts отдельно от app schemas

Pilot и дальнейший rollout должны явно разделить:

- app schemas / read models;
- API-localized envelopes;
- HA-facing payload shapes.

Нельзя расширять current app-level `schemas.py` как будто это универсальный contract layer на все поверхности.

## Locale и configuration policy

### Canonical locale model

Целевой supported set:

- `ru`
- `en`
- `es`
- `uk`

IRIS должен жить в BCP 47 логике. Значение `ua` не является language subtag и не должно быть canonical output.

Допустимый migration path:

- временно принимать `ua` как input alias;
- нормализовать его в `uk`;
- не хранить и не эмитить `ua` как effective locale.

### Repo-level settings

Недостаточно одного `IRIS_LANGUAGE`.

Целевая конфигурация:

- `IRIS_DEFAULT_LOCALE`
- `IRIS_SUPPORTED_LOCALES`
- `IRIS_FALLBACK_LOCALE`

Допустимо сохранить существующее поле `language` только как временный compatibility alias до полной миграции settings layer.

### Resolution order

1. Explicit locale override на surface.
2. Stored integration/user preference, если такой слой появится.
3. `Accept-Language` для HTTP.
4. Instance default locale.
5. Fallback locale.

Все входы нормализуются к supported locale set.

### Surface-specific overrides

Для старта достаточно определить:

- `Accept-Language`;
- explicit header override, например `X-IRIS-Locale`;
- explicit query override `?locale=...`;
- target-specific preference later.

## Cache и OpenAPI policy

Localization нельзя накладывать поверх текущих read endpoints без transport-safe semantics.

### 1. Stable contract per endpoint

На старте не надо делать “два режима на одном endpoint”.

Причины:

- fixed `response_model` уже участвует в governance;
- committed OpenAPI snapshots должны оставаться стабильными;
- analytical cache semantics не готовы к locale-dependent payload variance.

Практическое правило:

- либо endpoint остается canonical-only;
- либо появляется explicit localized read contract для этого endpoint surface.

### 2. Language-aware cache semantics

Как только endpoint рендерит locale-dependent narration, он обязан учитывать язык в caching policy:

- `Vary: Accept-Language, Accept, If-None-Match`
- locale-aware ETag
- locale-aware 304 semantics

Если этого нет, система начнет отдавать:

- неправильный язык из cache;
- некорректные 304;
- stale locale variants под одним и тем же ETag.

### 3. Snapshot surfaces

Для analytical snapshot surfaces локализация не отменяет уже существующие требования:

- `generated_at`
- `consistency`
- `freshness_class`
- `staleness_ms`
- `ETag`
- `Last-Modified`

Locale становится еще одним dimension того же transport contract.

## Formatting policy

Localization без formatting policy быстро развалится.

Нужно формально определить:

- decimal separator;
- thousands separator;
- percentage rendering;
- signed delta rendering;
- count / pluralization policy;
- list formatting policy;
- timeframe label policy;
- human duration rendering;
- datetime/timezone policy.

Правило одно:

- в `message_params` лежит семантическое значение;
- форматирование делает translator/formatter layer.

## Persisted artifacts policy

Хранить только `message_key + params` полезно, но недостаточно для audit-heavy surfaces.

Если catalog со временем изменится, старый artifact начнет рендериться по-новому.

Поэтому для persisted notifications, operation history и аналогичных исторических поверхностей нужен минимум один из вариантов:

- `catalog_version`;
- materialized render snapshot рядом с descriptor;
- оба варианта для особенно audit-sensitive surfaces.

Минимальный persisted descriptor:

- `message_key`
- `message_params`
- `surface`
- `variant`
- `catalog_version`
- optional `rendered_locale`
- optional `rendered_text_snapshot`

## HA-specific policy

Нужно жестко разделить два класса текста.

### 1. HA-side static integration strings

Это responsibility самой HA integration:

- entity labels;
- config-flow labels;
- diagnostics/static descriptions.

Для этого позже нужны `strings.json` / `translations/*`.

### 2. Backend-rendered business narration

Это responsibility backend:

- decision explanations;
- final signal narration;
- operation-like market outcomes;
- domain-driven notifications.

HA не должна собирать business message из raw fields вручную.

### HA payload rule

HA backend payload обязан содержать:

1. machine truth для automation;
2. descriptor / localized narration для человека.

Текущая text-first передача `reason` в `iris.decision` и `iris.investment_signal` считается legacy path и должна быть включена в migration plan.

## Legacy message bus policy

`runtime/streams/messages.py` сейчас живет в text-first модели:

- `AnalysisMessage.text`
- hardcoded English console/debug strings

Это нельзя оставить как вторую narration system.

Требование плана:

- либо legacy message bus переводится на descriptor-based payload;
- либо текстовая модель получает explicit deprecation path и исключается из canonical narration surfaces.

Без этого IRIS получит две параллельные модели человеческого текста:

- descriptor-based для API/HA;
- text-based для legacy bus.

## Operations и shared HTTP contracts

Operation/status narration входит в scope, но **не в pilot wave**.

Сейчас shared contracts вроде `AcceptedResponse.message` еще text-first.

Следствие:

- локализация operation/status flows потребует изменения shared HTTP contracts;
- это не надо смешивать с первым pilot rollout на read presenters;
- accepted/job/operation surfaces идут отдельной волной после стабилизации descriptor model.

## Relation to AI layer

AI humanization не должна быть первым шагом мультиязычности.

Сначала нужен deterministic backend narration layer.

Только после этого AI может:

- перефразировать;
- расширять explanation;
- адаптировать tone;
- строить briefs поверх canonical descriptor layer.

Но AI не должен подменять:

- `message_key`
- `reason_code`
- `status_code`
- canonical event payload

## Почему не `gettext` как в Django

Django-style `gettext` хорош для:

- server-rendered templates;
- forms/static UI labels;
- view-level translation.

Но для IRIS он не должен быть primary architecture:

- backend у нас typed API-first, а не HTML-first;
- value лежит в business narration, а не в статических шаблонах страниц;
- нам нужны machine codes и localized text одновременно;
- нам нужна transport-safe cache/OpenAPI policy, а не только string lookup.

Поэтому для IRIS правильнее:

- catalog-based translator;
- typed descriptors;
- boundary localization;
- optional richer ICU/Babel-like formatting позже.

## Предлагаемая файловая структура

Минимальный practical target:

```text
src/core/i18n/
  contracts.py
  locale.py
  resolver.py
  translator.py
  formatting.py
  catalogs/
    en.py
    ru.py
    es.py
    uk.py

src/apps/signals/narratives/
  decision_messages.py
  fusion_messages.py

src/apps/portfolio/narratives/
  action_messages.py

src/apps/anomalies/narratives/
  anomaly_messages.py

src/apps/market_structure/narratives/
  regime_messages.py

src/apps/signals/api/localized_contracts.py
src/apps/portfolio/api/localized_contracts.py
```

Если домену не нужен package, допустим один `narratives.py`, но не inline strings в services.

## Rollout plan

### Wave 0. Canonical taxonomy first

- [ ] formalize `reason_code / status_code / severity_code / action_code` for pilot domains;
- [ ] сделать mapping от текущих `reason: str` к canonical reason taxonomy;
- [ ] в pilot domains оставить legacy `reason` только как deprecated compatibility field;
- [ ] зафиксировать migration matrix для shared fields.

### Wave 1. Transport-safe foundations

- [ ] ввести `core/i18n` contracts, translator, resolver и formatter;
- [ ] зафиксировать catalog format;
- [ ] ввести repo-level locale settings;
- [ ] перейти на canonical `uk` и определить alias policy для legacy `ua`;
- [ ] обновить cache semantics для locale-aware surfaces;
- [ ] определить stable localized endpoint contract strategy без dual-mode shape на одном endpoint.

### Wave 2. Presenter-layer pilot

- [ ] начать только с `signals` и `portfolio`;
- [ ] ввести pure narrative descriptor builders;
- [ ] вынести localized API contracts отдельно от app schemas;
- [ ] локализовать boundary через presenters, не трогая services/engines;
- [ ] сохранить automation-safe machine fields.

### Wave 3. HA and legacy bus cleanup

- [ ] перевести HA-facing business payloads на descriptor-based model;
- [ ] определить, какие строки остаются HA-side static integration strings;
- [ ] убрать reliance на raw `reason` в HA events;
- [ ] включить `runtime/streams/messages.py` в descriptor migration или explicit deprecation path.

### Wave 4. Operations and shared HTTP contracts

- [ ] локализовать accepted/job/operation narration;
- [ ] обновить shared HTTP contracts, где сейчас живет `message: str`;
- [ ] определить policy для persisted operation history и materialized render snapshots.

### Wave 5. Expansion

- [ ] расширить descriptor model на `market_structure`, `anomalies`, затем `predictions` и `cross_market`;
- [ ] подключить тот же locale contract к lazy-investor / AI layer;
- [ ] не допускать AI-only narration без canonical descriptor underneath.

## Architecture checks

Когда слой стабилизируется, полезны automated checks:

- services/engines не импортируют translator напрямую;
- pilot domains больше не опираются на raw `reason: str` как source-of-truth;
- API-localized contracts отделены от app schemas;
- locale-aware endpoints используют `Accept-Language`-aware cache semantics;
- catalogs покрывают обязательные keys;
- canonical output never emits `ua`, only normalized `uk`;
- missing translation дает typed fallback, а не silent empty string;
- persisted audit-heavy artifacts несут `catalog_version` или materialized render snapshot.

## Definition of done

Backend business localization считается внедренной правильно только если:

- pilot domains перестали зависеть от raw `reason` как canonical explanation field;
- machine contracts остались language-neutral;
- localized narration строится отдельным pure layer;
- localized API contracts отделены от app schemas/read models;
- locale выбирается формально и предсказуемо;
- locale-aware reads не ломают OpenAPI и cache semantics;
- HA получает и machine fields, и human-readable business narration;
- legacy text-first bus не живет параллельной “второй системой” без migration policy;
- backend может рендерить минимум `ru/en/es/uk`;
- никакой domain engine не знает о переводах;
- AI layer не подменяет deterministic localization.

## Главный вывод

Для IRIS правильный путь не “перевести reason-строки” и не “размазать `_()` по сервисам”.

Правильный путь:

- сначала formalize canonical taxonomy;
- потом ввести transport-safe localization foundation;
- потом локализовать boundary presenters на pilot domains;
- только после этого переносить модель в HA, legacy bus и shared operation surfaces.

Именно это совместимо с текущей архитектурой IRIS и не ломает уже вычищенные service/runtime boundaries.
