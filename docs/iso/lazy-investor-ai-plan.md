# IRIS Lazy Investor AI Plan

## Статус

Этот документ больше не является абстрактным vision doc.

Его задача: зафиксировать, как AI-layer должен встраиваться в **уже принятую** архитектурную модель IRIS:

- service/engine split;
- runtime policies;
- performance budgets;
- mode/profile-aware HTTP surface;
- control-plane governed event routing.

Это bridge-документ между текущим `hypothesis_engine` и будущим `core.ai` / product AI capabilities.

Дальше из него должны родиться уже нормативные артефакты:

- `docs/architecture/adr/0015-ai-platform-layer.md`
- `docs/architecture/ai-runtime-policies.md`
- `docs/architecture/ai-performance-budgets.md`
- короткий rollout/audit doc под execution work.

## Цель

Собрать единый AI-layer для IRIS, который:

- не ограничивается только `hypothesis_engine`;
- умеет работать с несколькими реальными providers;
- включается capability-by-configuration, а не через один boolean feature flag;
- используется для `hypothesis_generate`, `notification_humanize`, `brief_generate`, `explain_generate`;
- уважает язык из instance settings или явно переданный `language` / `locale` для конкретного ответа;
- не ломает уже вычищенную service/runtime governance-модель;
- не превращает deterministic domains в LLM-first систему.

Это должен быть не “ещё один AI app”, а нормальный platform layer для продуктового сценария “ленивый инвестор”.

## Архитектурный контекст репо

AI-план обязан жить внутри уже принятой operating model проекта.

Связанные документы:

- `docs/iso/service-layer-refactor-audit.md`
- `docs/architecture/service-layer-runtime-policies.md`
- `docs/architecture/service-layer-performance-budgets.md`
- `docs/architecture/adr/0010-caller-owns-commit-boundary.md`
- `docs/architecture/adr/0011-analytical-engines-never-fetch.md`
- `docs/architecture/adr/0012-services-return-domain-contracts.md`
- `docs/architecture/adr/0013-async-classes-for-orchestration-pure-functions-for-analysis.md`
- `docs/architecture/adr/0014-post-commit-side-effects-only.md`
- `docs/architecture/adr/0003-control-plane-event-routing.md`
- `docs/architecture/adr/0008-research-vs-production-runtime.md`
- `docs/iso/backend-business-localization-plan.md`

Из этого следуют ограничения:

- AI должен лечь в `core/`, `apps/`, `runtime/`, а не строить параллельную архитектуру;
- AI-governance должен использовать ту же модель policy docs и ADR package;
- все тяжелые AI paths должны подчиняться runtime idempotency/retry/concurrency rules;
- AI surfaces должны уважать существующую mode/profile-aware HTTP model;
- briefs и AI-derived reads должны встраиваться в analytical snapshot semantics, а не жить отдельным “AI island”.

## Текущее состояние репо

Сейчас в проекте уже есть working AI-контур, но он ещё не platform-grade.

Что уже есть:

- `src/apps/hypothesis_engine`;
- prompt storage / activation;
- provider adapters `openai_like`, `local_http`, `heuristic`;
- generation flow для hypotheses;
- deterministic evaluation job для hypotheses;
- read surface, job trigger и SSE insights.

Главные текущие architectural debts:

1. `enable_hypothesis_engine` всё ещё является главным switch.

Этот флаг влияет не только на settings, но и на:

- router assembly;
- worker group registration;
- scheduler registration.

То есть migration должна затронуть runtime целиком, а не только config model.

2. Prompt data и infra routing сейчас слишком близко.

Сегодня prompt-layer уже может влиять на provider selection через `vars_json`, а provider factory параллельно читает infra config из settings. Это плохая граница.

Prompt не должен управлять:

- provider enablement;
- endpoint;
- auth token;
- network routing.

3. `HYPOTHESIS_OUTPUT_SCHEMA` пока не является настоящим output contract enforcement.

Сейчас это скорее “prompt asks for JSON”, чем строгий validated result.

Нужен отдельный validator path:

- provider output;
- schema/typed validation;
- explicit `validation_status`;
- fallback / reject semantics.

4. Heuristic fallback сейчас слишком магический.

Он полезен как degraded strategy, но он не должен считаться полноценным AI provider и скрывать деградацию capability.

5. Generation и evaluation conceptually разные, но в продуктовой модели пока названы слишком общо.

`hypothesis_generate` — AI capability.

`hypothesis_evaluation` — deterministic lifecycle job и не должен зависеть от availability реального provider.

## Главный архитектурный принцип

AI здесь не “новая бизнес-логика”.

AI — это следующий слой поверх уже существующих machine-canonical domains.

То есть:

- `signals`, `predictions`, `cross_market`, `portfolio`, `anomalies`, `market_structure` продолжают считать сами;
- AI работает поверх typed facts, событий и read models;
- AI объясняет, очеловечивает, суммирует, строит hypothesis и briefs;
- но не становится источником trading truth.

## Non-Negotiable правила

### 1. Deterministic domains остаются canonical

LLM не заменяет:

- signal scoring;
- prediction evaluation;
- anomaly detection;
- cross-market relation math;
- portfolio action calculation;
- market regime computation.

Все automation-critical outputs остаются deterministic.

### 2. LLM adapters не живут в domain services

Запрещено тащить `httpx/OpenAI/Ollama/provider SDK` в:

- `signals/services/*`
- `portfolio/services.py`
- `cross_market/services/*`
- любые другие domain orchestration services.

Все внешние AI вызовы должны жить в shared AI platform layer.

### 3. Feature flag убирается как primary source of truth

Capability считается доступной только если:

- есть реально сконфигурированный provider;
- этот provider разрешен для capability;
- runtime policy допускает исполнение capability в текущем mode/profile;
- health/degraded state не запрещает запуск.

Один boolean вроде `enable_hypothesis_engine` больше не должен решать судьбу целого AI слоя.

### 4. Prompt не управляет infra routing

Prompt и prompt vars могут хранить только:

- semantic context defaults;
- style profile;
- task-specific knobs, безопасные для исполнения.

Prompt не должен хранить и изменять:

- `base_url`
- `endpoint`
- `auth_token`
- `auth_header`
- `provider enablement`
- network routing

### 5. Heuristic fallback — это degraded strategy, а не равноправный provider

Rule-based fallback полезен, но он не должен:

- считаться “AI enabled”;
- скрывать provider outage;
- сидеть в том же logical family, что реальные LLM providers;
- автоматически маскировать validation/network/runtime failure.

### 6. Structured-first, humanized-second

Во всех AI use cases первичен typed contract.

Сначала:

- machine event;
- deterministic context bundle;
- typed AI input/output contract.

Потом:

- humanized text;
- summary;
- brief;
- expanded explanation.

### 7. AI execution обязан уважать language / locale contract

AI-capability не должна сама “угадывать” язык ответа.

Источник языка обязан быть формальным и предсказуемым:

- explicit `language` / `locale`, переданный для конкретного запроса, job trigger или delivery target;
- stored preference target-а, если такой слой появится;
- instance default language из settings;
- fallback `en`, если ничего больше не задано.

Для текущего состояния IRIS это означает минимум:

- `settings.language` является instance default;
- AI execution может принять explicit requested language;
- итоговый humanized / brief / explain output обязан быть сгенерирован именно на effective language, а не “на языке модели по умолчанию”.

Machine-canonical fields при этом остаются language-neutral.

### 8. Context serialization — это отдельный execution concern

Typed context bundle не должен напрямую утекать в prompt как “что получилось”.

Сначала:

- deterministic context builder собирает typed facts;
- execution layer выбирает context transport format;
- только потом context serializes-ится в prompt input.

Формат передачи контекста должен быть явным и policy-driven, а не случайным следствием того, как данные сейчас выглядят в Python.

## Capability model

Top-level capabilities должны быть компактными.

На platform-уровне:

- `hypothesis_generate`
- `notification_humanize`
- `brief_generate`
- `explain_generate`

Детализация должна жить не в раздувании capability registry, а во typed input/output:

- `brief_kind = market | symbol | portfolio`
- `explain_kind = signal | decision`
- `hypothesis_source = signal_created | anomaly_detected | ...`

Это удерживает config/routing surface маленьким и управляемым.

## Capability, task, prompt, provider: чёткое разведение

Система должна различать четыре разные сущности.

### Capability

Это runtime/policy/exposure unit.

Capability определяет:

- кто вообще может быть запущен;
- какие providers разрешены;
- какие execution modes допустимы;
- какой degraded policy действует;
- какие API/runtime surfaces публикуются.

### Task

Это конкретный prompt contract внутри capability.

Примеры:

- `hypothesis.signal_created`
- `hypothesis.anomaly_detected`
- `notification.decision_generated`
- `brief.market.daily`

`task` — это не provider routing и не feature flag.

### Prompt

Это versioned template/schema/style artifact для task.

Prompt отвечает за:

- wording;
- expected output shape identifier;
- style/tone constraints;
- semantic defaults, безопасные для domain.

### Provider

Это infrastructure adapter:

- endpoint;
- auth policy;
- model;
- timeout;
- concurrency/cost/latency class;
- supported capabilities.

## Language / locale contract

Язык должен быть частью AI execution contract, а не неявной prompt-магией.

### Resolution order

1. Explicit requested language для текущего ответа.
2. Delivery-target or integration preference.
3. `settings.language` как instance default.
4. Fallback `en`.

### Prompt interaction

Prompt может использовать language только как semantic execution input:

- для выбора wording;
- для выбора tone/profile;
- для language-aware output schema constraints.

Prompt не должен сам выбирать effective language вопреки execution contract.

### Execution metadata

Каждый AI result должен различать:

- `requested_language`
- `effective_language`

Это нужно для:

- auditability;
- deterministic replay;
- правильной деградации;
- HA / API delivery semantics.

### Output rule

Если capability возвращает human-facing text, он обязан быть на `effective_language`.

Недопустимо:

- silently ответить на языке provider default;
- partially mixed-language output без явного режима;
- потерять информацию о том, почему выбран конкретный язык.

## Context transport contract

Явная политика передачи контекста в AI execution обязательна.

### Общий принцип

Внутри доменов source of truth остаётся typed context bundle.

На boundary между domain layer и AI execution этот context преобразуется в один из поддерживаемых transport formats:

- `json`
- `compact_json`
- `toon`
- `csv`

Это решение принимает execution layer по policy, а не domain service и не сам prompt.

### Практическое правило выбора

- `json` — когда нужен максимум совместимости и простоты пайплайна.
- `compact_json` — когда pipeline уже работает на JSON, но нужно срезать мусор и уменьшить context size.
- `toon` — когда в prompt часто уходят большие массивы однотипных объектов: логи, свечи, транзакции, таблицы сигналов, портфели, метрики.
- `csv` — когда данные реально являются плоской таблицей и не нужна вложенность.

### Формальные правила

1. Default baseline format — `json`.
2. `compact_json` допустим для nested structured payloads, если это уменьшает шум без потери semantics.
3. `toon` должен использоваться только для repeatable row-like objects с устойчивой колонковой формой.
4. `csv` не должен использоваться для data with meaningful nesting, optional deep fields или graph-like relations.
5. Один и тот же `task` должен иметь ограниченный whitelist допустимых context formats, а не arbitrary serialization.
6. Prompt не должен сам сериализовать context; он получает уже готовый serialized input и metadata о формате.

### Почему это важно

Без этой policy система скатится в смесь:

- raw dict dumps;
- случайных compacted payloads;
- prompt-specific hacks;
- разных ad-hoc таблиц для одинаковых data classes.

Это ломает:

- repeatability;
- observability;
- token budgeting;
- validator assumptions;
- cross-provider consistency.

### Prompt/task interaction

`task` должен уметь задать:

- preferred context format;
- allowed context formats;
- max context budget constraints.

Но итоговый effective format всё равно должен выбирать execution layer.

### Execution metadata

Каждый AI execution result желательно связывать с:

- `context_format`
- `context_record_count`
- `context_bytes`
- optional `context_token_estimate`

Это нужно для:

- budget control;
- explainability;
- perf tuning;
- provider comparison;
- deterministic replay.

## Provider model

Вместо рассыпанных settings нужен typed provider registry.

Пример одной записи:

```json
{
  "name": "openai_primary",
  "kind": "openai_like",
  "enabled": true,
  "base_url": "https://api.openai.com/v1",
  "endpoint": "/chat/completions",
  "auth_token": "env:OPENAI_API_KEY",
  "auth_header": "Authorization",
  "auth_scheme": "Bearer",
  "model": "gpt-4.1-mini",
  "timeout_seconds": 15,
  "priority": 100,
  "capabilities": [
    "hypothesis_generate",
    "notification_humanize",
    "brief_generate",
    "explain_generate"
  ]
}
```

Дополнительно нужны:

- `metadata` для latency/cost/compliance tiers;
- optional `max_context_tokens`, `max_output_tokens`;
- health status;
- capability-specific overrides при необходимости.

### Requested vs actual provider

Каждый execution result должен различать:

- `requested_provider`
- `actual_provider`
- `requested_language`
- `effective_language`

Это нужно для fallback, observability и auditability.

## Output contract enforcement

Prompt “верни JSON” недостаточно.

Нужен настоящий schema-first execution path:

1. provider returns raw payload;
2. payload parsing;
3. schema / typed validator;
4. bounded normalization only after validation;
5. explicit `validation_status`.

Минимальные статусы:

- `valid`
- `invalid_schema`
- `invalid_semantics`
- `fallback_applied`
- `rejected`

LLM output не должен silently превращаться в “что-то похоже на ответ”.

Для language-aware capabilities validator также должен проверять, что output совместим с requested/effective language policy там, где это применимо.

Execution layer также должен проверять, что выбранный `context_format` допустим для текущего `task` и capability policy.

## Shared AI platform layer

Первый реальный безопасный шаг — это не новый большой app, а общий `core.ai`.

Целевая структура:

```text
src/core/ai/
  contracts.py
  capabilities.py
  settings.py
  provider_registry.py
  provider_router.py
  executor.py
  validators.py
  telemetry.py
  degraded_modes.py
  health.py
  providers/
    base.py
    openai_like.py
    local_http.py
```

Роль:

- typed registry of configured providers;
- capability-aware provider routing;
- execution with validation;
- degraded-mode handling;
- typed telemetry envelope;
- health and readiness model.

### Что переносится первым

Первый кодовый рефактор должен быть узким:

- `apps/hypothesis_engine/providers/*` → `core/ai/providers/*`
- provider factory → `core/ai/provider_registry.py`
- `ReasoningService` становится thin orchestration над `AIExecutor.execute(...)`

Это даст platform layer без большого rename domain app.

## Что делать с текущим `hypothesis_engine`

Не нужно начинать с большого rename в `lazy_investor`.

Текущий правильный путь:

### Phase 1

Сохранить `src/apps/hypothesis_engine` как domain app, но перевести его на shared `core.ai`.

### Phase 2

Добавить новую capability `notification_humanize` поверх shared platform.

### Phase 3

Добавить `brief_generate` уже как analytical snapshot surface.

### Phase 4

Только когда стабилизированы минимум две новые реальные capabilities, решать:

- нужен ли отдельный `src/apps/lazy_investor`;
- или capabilities лучше остались распределены по domain/product apps поверх `core.ai`.

Прямое правило:

**не создавать большой `apps/lazy_investor` только ради красивого имени.**

## Generation vs evaluation: явное разделение

Нужно зафиксировать это как архитектурный инвариант.

### `hypothesis_generate`

Это AI capability:

- зависит от provider availability;
- использует prompt/task/provider routing;
- публикует AI-derived artifact.

### `hypothesis_evaluation`

Это deterministic service lifecycle:

- использует обычный job + lock + tracked operation;
- не зависит от availability реального LLM provider;
- не отключается вместе с generation surfaces;
- сохраняет наблюдаемость даже если AI generation временно offline.

Read surfaces для hypotheses и evaluations не должны исчезать только из-за отсутствия provider.

## Runtime gating: не только settings

Migration на capability-by-configuration обязана затронуть три слоя сразу:

1. **Router assembly**
   Что монтируется в `full`, `local`, `ha_addon`.

2. **Worker registration**
   Какие worker groups вообще существуют в runtime.

3. **Scheduler registration**
   Какие background jobs включаются автоматически.

AI availability не должна решаться в одном месте и обходиться в двух других.

## Mode/Profile matrix

AI-spec обязан быть mode-aware.

Минимальная целевая матрица:

| Surface | `full` | `local` | `ha_addon` / `HA_EMBEDDED` |
| --- | --- | --- | --- |
| hypothesis read surfaces | yes | yes | yes |
| hypothesis generation trigger | yes | yes | no |
| hypothesis evaluation job trigger | yes | yes | no public trigger |
| AI insight streams | yes | yes | no |
| provider/prompt operator admin | yes | yes | no |
| humanized notification delivery | yes | yes | yes, if upstream bridge exists |
| brief read surfaces | yes | yes | selected cached reads only |
| brief generation trigger | yes | yes | no |

Принцип:

- human-facing reads могут существовать без generation;
- generation/admin/streaming не обязаны быть доступны в HA embedded profile;
- public availability должна следовать той же governance-модели, что и остальной HTTP surface.

## Failure domains и degraded modes

Нужен явный operational model.

### `healthy`

- есть хотя бы один real provider;
- validation path работает;
- capability исполняется в normal mode.

### `degraded`

- primary provider unavailable;
- fallback chain используется;
- или capability временно разрешена только через deterministic degraded strategy.

Примеры:

- `notification_humanize` может деградировать в template-based humanization;
- `explain_generate` может деградировать в bounded deterministic summary;
- `hypothesis_generate` по умолчанию не должен silently деградировать в псевдо-LLM, если это продуктово недопустимо.

### `offline`

- нет доступных real providers;
- generation capabilities не исполняются;
- read surfaces остаются;
- deterministic evaluation paths продолжают работать;
- runtime отдает typed `unavailable` / `skipped`, а не делает вид, что всё ок.

## Не блокировать остальной runtime

Это отдельный архитектурный инвариант.

Тяжелые AI capabilities никогда не должны садиться на общие analytical worker lanes.

Правило:

- отдельные AI worker groups;
- отдельные concurrency budgets;
- отдельные timeout/perf budgets;
- никакого влияния AI outage на deterministic signal/prediction/portfolio paths.

Если сейчас `hypothesis` уже partly изолирован отдельной worker group, это направление нужно сохранить и formalize-ить.

## Storage и observability

Не нужен один универсальный `AIArtifact` storage “на всё сразу”.

`hypotheses`, `notifications`, `briefs` имеют разный lifecycle и не должны насильно сшиваться в одну таблицу только ради абстракции.

Что нужно сделать вместо этого:

- сохранить artifact-specific storage;
- стандартизовать общий execution metadata envelope.

Минимальные metadata fields:

- `capability`
- `task`
- `requested_provider`
- `actual_provider`
- `requested_language`
- `effective_language`
- `context_format`
- `context_record_count`
- `context_bytes`
- `fallback_used`
- `degraded_strategy`
- `latency_ms`
- `validation_status`
- `prompt_name`
- `prompt_version`
- `source_event_type`
- `source_event_id`
- `source_stream_id`
- `causation_id`
- `correlation_id`

Для hypotheses это не редизайн, а расширение уже хорошей traceability базы.

Минимальные метрики:

- calls by capability/provider;
- error rate;
- fallback rate;
- validation failure rate;
- p95/p99 latency by capability;
- queue depth / saturation for AI workers.

## Notification humanization как первая новая capability

Первой новой capability после migration должен быть не `brief_generate`, а `notification_humanize`.

Почему:

- короткий context;
- короткий output;
- простой typed artifact;
- легко наблюдать degraded mode;
- не требует сразу сложной query/cache/freshness модели;
- естественно ложится на уже существующий event-driven flow.

Целевой вход:

- `signal_created`
- `decision_generated`
- `anomaly_detected`
- `market_regime_changed`
- `portfolio_position_changed`
- `portfolio_balance_updated`

Целевой выход:

- short title;
- humanized message;
- urgency/severity tag;
- output language aligned with requested/effective language;
- structured refs back to source event and canonical machine fields.

## Briefs как analytical snapshot surface

`brief_generate` нельзя проектировать как “магический AI endpoint”.

В рамках текущей API governance модели IRIS briefs должны быть analytical snapshot surface:

1. deterministic context bundle;
2. tracked async generation job;
3. stored/cached brief artifact;
4. read surface with freshness metadata.

Для brief read surface должны быть продуманы:

- `operation_id` для generation trigger;
- `generated_at`;
- `consistency`;
- `freshness_class`;
- `staleness_ms`;
- `ETag`;
- `Last-Modified`.

Только так briefs встроятся в уже существующую HTTP/API governance модель проекта.

## Operator/admin surface

Prompt/provider/operator control не должен уходить в отдельную “AI админку ради AI админки”.

Target policy:

- AI operator/admin surfaces должны интегрироваться с existing control-plane/operator model;
- prompt/provider health/config governance лучше вешать на existing operator surfaces;
- AI platform не должен плодить параллельный административный срез без необходимости.

## Prompt policy

Prompt management должно быть capability-aware и task-aware.

Обязательные поля prompt metadata:

- `task`
- `prompt_name`
- `version`
- `schema_contract`
- `style_profile`

Допустимые prompt vars:

- semantic defaults;
- style/tone knobs;
- safe rendering hints.

Недопустимые prompt vars:

- network config;
- secrets;
- auth;
- endpoint selection;
- provider enablement.

Если prompt влияет на business semantics, это должно быть traceable и reviewable.

## Rollout plan

### Stage 1. Governance and foundations

- [ ] закрепить AI-layer как часть текущей architecture family, а не отдельную конституцию;
- [ ] подготовить ADR + runtime policy + performance budgets package;
- [ ] определить compact capability taxonomy;
- [ ] определить capability/task/prompt/provider model;
- [ ] определить context transport policy и format selection matrix;
- [ ] определить degraded-mode policy.

### Stage 2. `core.ai` foundation

- [ ] ввести typed provider registry в `core.ai`;
- [ ] добавить `auth_token`, `auth_header`, `auth_scheme`;
- [ ] добавить provider routing по capability;
- [ ] добавить context serializer/renderer для `json`, `compact_json`, `toon`, `csv`;
- [ ] добавить strict output validator;
- [ ] добавить typed telemetry envelope.

### Stage 3. Hypothesis migration

- [ ] перенести providers из `apps/hypothesis_engine` в `core.ai`;
- [ ] перевести `ReasoningService` на `AIExecutor.execute(capability="hypothesis_generate", ...)`;
- [ ] разрезать prompt semantics и infra routing;
- [ ] заменить boolean flag на capability-aware router/worker/scheduler gating;
- [ ] сохранить read surfaces даже при отсутствии generation capability;
- [ ] явно отделить `hypothesis_generate` от `hypothesis_evaluation`.

### Stage 4. Notification humanization

- [ ] добавить `notification_humanize`;
- [ ] определить typed notification artifact;
- [ ] определить event scope, throttling и degraded strategy;
- [ ] изолировать execution на dedicated worker lanes.

### Stage 5. Briefs

- [ ] добавить `brief_generate`;
- [ ] спроектировать deterministic context bundles;
- [ ] определить preferred transport formats для brief contexts, включая `toon` / `csv` там, где это оправдано;
- [ ] сделать generation tracked async operation;
- [ ] сделать stored/cached brief read surface с freshness metadata;
- [ ] не смешивать brief storage lifecycle с hypothesis/notification storage.

### Stage 6. Optional product-layer expansion

- [ ] вернуться к вопросу отдельного `apps/lazy_investor` только если уже есть минимум две новые устойчивые capability;
- [ ] не делать большой rename без явной product/ownership причины.

## Что сознательно не делаем прямо сейчас

- не вводим сразу DB-backed universal provider registry;
- не делаем большой rename `hypothesis_engine` → `lazy_investor`;
- не делаем общий “AIArtifact” storage на все случаи;
- не разрешаем prompt-ам управлять infra routing;
- не считаем heuristic fallback реальным AI provider;
- не проектируем briefs как sync magic answers без freshness/operation semantics.

## Definition of done

AI-layer считается доведённым до platform-grade состояния только если:

- он встроен в уже существующую governance system проекта;
- capability availability определяется provider registry + runtime policy, а не одним feature flag;
- router assembly, worker registration и scheduler registration используют одну capability model;
- language resolution определяется execution contract и `settings.language`, а не неявным provider default;
- prompt/task/provider строго разведены;
- output validation реально enforced;
- heuristic fallback перестал маскироваться под полноценный provider;
- generation и deterministic evaluation разведены явно;
- heavy AI work не блокирует общие analytical worker lanes;
- hypotheses/read surfaces сохраняют наблюдаемость даже при offline providers;
- briefs встроены в analytical snapshot semantics;
- новый product app не создан преждевременно только ради названия.

## Главный вывод

Следующий шаг для IRIS — не “добавить ещё пару prompt-ов” и не “сразу завести большой `lazy_investor` app”.

Следующий шаг:

- встроить AI в уже принятую governance-модель проекта;
- сначала сделать узкий и безопасный `core.ai`;
- перевести на него `hypothesis_engine`;
- первой новой capability сделать `notification_humanize`;
- briefs проектировать сразу как analytical snapshot surface;
- и только потом решать, нужен ли отдельный product app.

Именно это даст IRIS зрелый AI platform layer без возврата к architecture blur.
