# IRIS Backend Business Localization Plan

## Цель

Зафиксировать, как IRIS должен поддерживать мультиязычность на backend-уровне так, чтобы:

- пользователь понимал, что ему говорит система в API, event-stream, HA и notification surfaces;
- машинная бизнес-логика не размывалась переводами;
- уже принятый `service/engine` split не ломался;
- локализация была совместима с event-driven runtime, control plane и будущим AI-layer.

Этот документ описывает **backend business localization**, а не frontend i18n.

## Архитектурный контекст

План должен работать внутри уже принятых архитектурных ограничений:

- service layer и analytical engines уже разделены;
- side effects живут после commit;
- runtime event-driven и управляется control plane;
- Home Assistant является внешним automation/notification host;
- AI-layer рассматривается как отдельная capability и не должен подменять deterministic domain truth.

Связанные документы:

- `docs/iso/service-layer-refactor-audit.md`
- `docs/architecture/service-layer-runtime-policies.md`
- `docs/architecture/adr/0003-control-plane-event-routing.md`
- `docs/architecture/adr/0008-research-vs-production-runtime.md`
- `docs/iso/lazy-investor-ai-plan.md`

## Проблема

Сейчас backend mostly возвращает machine-oriented semantics:

- canonical event types;
- decision codes;
- status values;
- reason-like raw fields;
- операторские и системные тексты без формальной localization policy.

Для automation и internal wiring это правильно.

Но для человека этого недостаточно, особенно в HA и notification-like surfaces:

- пользователь видит system vocabulary вместо понятного сообщения;
- смысл бизнес-решения теряется без дополнительного human-readable narration;
- язык вывода не контролируется формально;
- перевод и business logic легко начинают смешиваться в одном и том же service code.

## Scope

Этот документ покрывает только backend-owned user-facing text:

- human-readable business messages в API responses;
- HA-facing messages и entity narration;
- event/SSE/push payloads, которые предназначены не только для машин, но и для пользователя;
- operation status narration;
- system-generated summaries, если они deterministic и backend-owned.

Этот документ **не** покрывает:

- frontend UI translations;
- перевод произвольного контента из БД;
- AI-generated freeform text как primary localization mechanism;
- перевод machine identifiers вроде `BUY`, `SELL`, `signal_created`, `market_regime_changed`.

## Основная идея

Переводится не сама бизнес-логика.

Переводится то, **что система говорит человеку о результатах этой логики**.

То есть:

- domain logic остаётся canonical и language-neutral;
- поверх неё появляется отдельный narration/localization layer;
- этот слой работает на boundary между machine contracts и user-facing outputs.

## Non-Negotiable правила

### 1. Machine contracts остаются источником истины

Канонические поля не должны зависеть от языка:

- `event_type`
- `decision`
- `status`
- `reason_code`
- `severity_code`
- `action_code`
- typed numeric/temporal fields

Automation, policies, routing и downstream integrations обязаны опираться именно на них.

### 2. Переводы не живут в engines

Pure engines и domain math не должны ничего знать о языке.

Запрещено:

- рендерить localized text внутри analytical engines;
- тащить translation lookup в scoring/detection logic;
- принимать locale как часть математического вычислительного контракта.

### 3. Переводы не живут в orchestration services как inline strings

Service может вернуть codes/facts/result contract.

Но service не должен превращаться в string-construction layer с разбросанными `if locale == ...`.

### 4. Localized text не заменяет machine shape

Нельзя отдавать только свободный текст без key/code/params.

Минимальный безопасный backend contract:

- machine fields;
- `message_key`;
- `message_params`;
- optional rendered `message`;
- effective `locale`.

### 5. Localization делается на boundary

Подходящие места:

- API presenters;
- HA adapters;
- notification dispatch adapters;
- SSE / stream presenters;
- dedicated narrative/presenter modules.

Неподходящие места:

- `engines/`
- repository layer;
- raw service orchestration;
- runtime consumer routing logic.

### 6. Stored artifacts по умолчанию хранят key+params, а не только готовый текст

Если хранить только готовую фразу, система теряет:

- смену locale при чтении;
- повторный рендер в другом языке;
- traceability между machine outcome и human message;
- safe future changes в catalogs.

## Целевая модель контракта

### Machine outcome

Это уже существующий typed result / read model / event payload.

Пример:

```json
{
  "decision": "BUY",
  "confidence": 0.82,
  "reason_code": "signals.regime_alignment.high",
  "symbol": "BTC",
  "timeframe": 60
}
```

### Message descriptor

Поверх него строится deterministic narration descriptor:

```python
@dataclass(frozen=True, slots=True)
class MessageDescriptor:
    key: str
    params: Mapping[str, object]
    severity: str | None = None
    audience: str | None = None
```

### Localized message

Boundary adapter затем рендерит локализованную форму:

```python
@dataclass(frozen=True, slots=True)
class LocalizedMessage:
    key: str
    locale: str
    text: str
    params: Mapping[str, object]
```

### Финальный user-facing payload

```json
{
  "decision": "BUY",
  "confidence": 0.82,
  "reason_code": "signals.regime_alignment.high",
  "message_key": "signals.decision.buy.regime_alignment_high",
  "message_params": {
    "symbol": "BTC",
    "timeframe_label": "1h",
    "confidence_pct": 82
  },
  "message": {
    "locale": "ru",
    "text": "BTC показывает сильное бычье подтверждение на таймфрейме 1h."
  }
}
```

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
    ua.py
```

Роль:

- определить supported locales;
- выбрать effective locale;
- рендерить `message_key + params -> text`;
- обеспечивать fallback;
- форматировать числа, проценты, даты и durations.

### 2. Domain narratives

В каждом домене, где нужен human-readable backend output, должен быть pure narration layer:

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
- не знать ничего о HTTP, HA, Redis Streams или provider SDK.

Это по сути тот же принцип, что и с `engine`:

- deterministic input;
- deterministic output;
- zero side effects.

### 3. Boundary adapters

Localization render должен жить в adapters/presenters:

- API presenters;
- HA bridge message presenters;
- notification presenters;
- SSE presenters.

Именно они:

- берут `MessageDescriptor`;
- выбирают locale;
- вызывают translator;
- добавляют rendered text в ответ или event payload.

## Locale resolution policy

На старте поддерживаем:

- `ru`
- `en`
- `es`
- `ua`

### Resolution order

1. Explicit locale на запросе / подписке / команде.
2. Stored user or integration preference, если такой слой появится.
3. Instance default language.
4. Fallback `en`.

### HTTP

Для HTTP допустимы:

- `Accept-Language`;
- explicit query/header override;
- instance default.

### Home Assistant

Для HA желательно поддерживать locale на уровне integration session/subscription.

Если HA locale не передан:

- используется instance default;
- machine fields всё равно остаются в payload.

### Async jobs and stored notifications

Для persisted artifacts по умолчанию хранится:

- `message_key`;
- `message_params`;
- optional `rendered_locale`, если сообщение materialized заранее.

Если сообщение рендерится в момент delivery, locale должен определяться delivery target-ом.

## Formatting policy

Localization без formatting policy быстро развалится.

Нужно формально определить:

- decimal separator;
- thousands separator;
- percent formatting;
- signed deltas;
- timeframe labels;
- human duration rendering;
- datetime/timezone rendering rules.

Пример:

- `0.8214` не должен вручную вшиваться в template;
- в `message_params` должен идти semantic value, а formatting делает translator/formatter layer.

## HA-specific policy

Для Home Assistant backend обязан отдавать одновременно:

1. machine truth для automation;
2. localized narration для человека.

### Пример HA event payload

```json
{
  "event_type": "decision_generated",
  "payload": {
    "decision": "BUY",
    "confidence": 0.82,
    "reason_code": "signals.regime_alignment.high",
    "message_key": "signals.decision.buy.regime_alignment_high",
    "message_params": {
      "symbol": "BTC",
      "timeframe_label": "1h"
    },
    "message": {
      "locale": "ru",
      "text": "BTC показывает сильное бычье подтверждение на таймфрейме 1h."
    }
  }
}
```

Правило:

- HA automations должны читать machine fields;
- HA cards/notifications могут показывать localized text;
- backend не должен заставлять HA парсить свободный текст обратно в бизнес-смысл.

## API policy

Backend API может поддерживать два режима:

### A. Canonical-only mode

Возвращаются только machine fields + `message_key/message_params`.

Подходит для:

- internal services;
- automation consumers;
- strict integration points.

### B. Canonical-plus-rendered mode

Возвращаются machine fields + `message_key/message_params` + rendered `message`.

Подходит для:

- operator UI;
- HA bridge;
- human-facing read surfaces.

На старте для простоты можно использовать только второй режим на selected endpoints.

## Где начинать

Не нужно пытаться перевести весь backend сразу.

Приоритеты должны идти по user-facing value:

### Wave 1

- `signals`
- `portfolio`
- `market_structure`
- `anomalies`

Это основные домены, которые чаще всего формируют action-oriented narration для HA и уведомлений.

### Wave 2

- `predictions`
- `cross_market`
- selected `control_plane` operator messages

### Wave 3

- operation progress/status surfaces;
- remaining operator/admin texts;
- deterministic summaries;
- AI layer integration on top of the same locale contract.

## Relation to AI layer

AI humanization не должна быть первым шагом мультиязычности.

Сначала нужен deterministic backend narration layer.

Только после этого AI может:

- перефразировать;
- расширять explanation;
- генерировать briefs;
- адаптировать tone.

Но AI не должен подменять:

- `message_key`;
- `reason_code`;
- `status_code`;
- canonical event payload.

Иначе localization превратится в непредсказуемую генерацию текста вместо архитектурно контролируемого слоя.

## Почему не `gettext` как в Django

Django-style `gettext` хорош для:

- server-rendered templates;
- форм с большим количеством статических UI labels;
- view-level translation.

Но для IRIS он не должен быть primary architecture:

- у нас typed API, а не HTML-first backend;
- у нас event-driven runtime и HA integration;
- большая часть ценности лежит не в переводе UI labels, а в переводе business narration;
- нам нужны machine codes + localized text одновременно.

Поэтому для IRIS правильнее:

- catalog-based translator;
- typed message descriptors;
- localization at boundaries;
- optional ICU/Babel-like formatting later.

Это не исключает `gettext` совсем, но не делает его основой модели.

## Предлагаемая файловая структура

Минимальный практичный старт:

```text
src/core/i18n/
  contracts.py
  locale.py
  resolver.py
  translator.py
  catalogs/
    en.py
    ru.py
    es.py
    ua.py

src/apps/signals/narratives/
  decision_messages.py
  fusion_messages.py

src/apps/portfolio/narratives/
  action_messages.py

src/apps/anomalies/narratives/
  anomaly_messages.py

src/apps/market_structure/narratives/
  regime_messages.py
```

Если какой-то домен не требует отдельного package, допустим один маленький `narratives.py`, но не string-literals inside services.

## Rollout plan

### Stage 1. Foundations

- [ ] зафиксировать этот документ как source-of-truth;
- [ ] ввести `core/i18n` contracts and translator;
- [ ] определить locale resolution policy;
- [ ] зафиксировать catalog format;
- [ ] определить formatting rules.

### Stage 2. Domain narration contracts

- [ ] ввести pure narrative descriptor builders в `signals`;
- [ ] сделать то же для `portfolio`;
- [ ] добавить narration для `market_structure` и `anomalies`;
- [ ] запретить direct translated strings inside services/engines.

### Stage 3. HA and API delivery

- [ ] добавить localized payload rendering в HA bridge;
- [ ] добавить canonical-plus-rendered contract на selected read surfaces;
- [ ] определить default locale behavior для HA sessions;
- [ ] протестировать automation compatibility.

### Stage 4. Operations and notifications

- [ ] локализовать operation status narration;
- [ ] локализовать notification/event presentation layer;
- [ ] определить policy для stored vs rendered-at-read artifacts.

### Stage 5. AI integration

- [ ] использовать тот же locale contract в lazy-investor / AI layer;
- [ ] не допускать AI-only narration без canonical fields;
- [ ] отделить deterministic narration от AI expansion.

## Architecture checks

Когда слой стабилизируется, полезны automated checks:

- services/engines не импортируют translator напрямую;
- domain services не возвращают только свободный текст вместо machine shape;
- boundary presenters умеют отдавать `message_key/message_params`;
- catalogs покрывают обязательные keys;
- missing translation дает typed fallback, а не silent empty string.

## Definition of done

Backend business localization считается внедрённой правильно только если:

- machine contracts остались language-neutral;
- localized narration строится отдельным pure layer;
- locale выбирается формально и предсказуемо;
- HA получает и machine fields, и human-readable text;
- backend может рендерить минимум `ru/en/es/ua`;
- никакой domain engine не знает о переводах;
- AI layer не подменяет deterministic localization.

## Главный вывод

Для IRIS правильный путь не “перевести всю бизнес-логику” и не “размазать `_()` по сервисам”.

Правильный путь:

- оставить business logic machine-canonical;
- ввести отдельный backend narration/localization layer;
- рендерить локализованный текст только на boundary;
- отдавать HA и другим human-facing surfaces одновременно и строгие коды, и понятное человеку сообщение.

Именно это совместимо с текущей архитектурой IRIS и не сломает уже вычищенные service/runtime boundaries.
