# IRIS Backend — Техническое ревью кода

**Дата:** 12 марта 2026  
**Ревьюер:** AI Code Review  
**Проект:** IRIS — Market Intelligence Service  
**Стек:** FastAPI, SQLAlchemy 2.0, TaskIQ, Redis Streams, TimescaleDB, Vue 3

---

## Содержание

1. [Общая оценка](#общая-оценка)
2. [Архитектура](#архитектура)
3. [Качество кода](#качество-кода)
4. [База данных и миграции](#база-данных-и-миграции)
5. [Тестирование](#тестирование)
6. [Runtime и оркестрация](#runtime-и-оркестрация)
7. [API дизайн](#api-дизайн)
8. [Безопасность](#безопасность)
9. [Производительность](#производительность)
10. [Наблюдаемость](#наблюдаемость)
11. [Docker и развёртывание](#docker-и-развёртывание)
12. [Приоритетные рекомендации](#приоритетные-рекомендации)

---

## Общая оценка

**Оценка: 7.5/10**

Это хорошо спроектированная, производственно-ориентированная кодовая база с отличным предметным моделированием и событийно-ориентированным дизайном. Основные пробелы находятся в области **безопасности, наблюдаемости и операционной готовности**, а не основной функциональности.

**Ключевые преимущества:**
- Предметно-ориентированный дизайн
- Событийная архитектура
- Комплексное тестирование
- Оптимизация TimescaleDB

**Ключевые риски:**
- Нет аутентификации
- Ограниченная наблюдаемость
- Захардкоженная конфигурация
- Нет стратегии продакшен-развёртывания

---

## Архитектура

### Сильные стороны ✅

| Аспект | Описание |
|--------|----------|
| **Domain-Driven Design** | Чёткое разделение на `src/apps/` (market_data, indicators, patterns, signals, portfolio и т.д.) |
| **Event-Driven Architecture** | Redis Streams для слабосвязанного аналитического конвейера |
| **Современный стек** | FastAPI, SQLAlchemy 2.0, TaskIQ, Pydantic Settings, uv package manager |
| **Гибридная модель** | Polling для приёма данных + событийная обработка для внутренней аналитики |
| **Документация** | Обстоятельная документация в README.md и CHANGELOG.md |

### Проблемные моменты ⚠️

| Проблема | Файл | Критичность |
|----------|------|-------------|
| Риск циклических импортов | `src/core/bootstrap/app.py` | Средняя |
| Смешанные sync/async паттерны | `src/apps/market_data/service_layer.py` | Средняя |
| Монолитный планировщик | `src/runtime/scheduler/runner.py` | Низкая |

**Детали:**

```python
# src/core/bootstrap/app.py — манипуляции sys.path для Alembic
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_ORIGINAL_SYS_PATH = list(sys.path)
sys.path = [path for path in _ORIGINAL_SYS_PATH if ...]
from alembic.config import Config
import alembic.command as command
sys.path = _ORIGINAL_SYS_PATH
```

```python
# src/apps/market_data/service_layer.py — asyncio.run() в sync контексте
fetch_result = asyncio.run(carousel.fetch_history_window(coin, interval, start, latest_available))
```

---

## Качество кода

### Критические нарушения (124 linting violations)

#### 1. Неопределённые имена в `__all__` (F822) — 3 случая

| Файл | Строка | Проблема |
|------|--------|----------|
| `src/apps/indicators/analytics.py` | 355 | `list_coin_metrics` |
| `src/apps/signals/services.py` | 717 | `list_enriched_signals` |
| `src/apps/signals/services.py` | 717 | `list_top_signals` |

#### 2. Нарушения порядка импортов (E402) — 45 случаев

**Основной файл:** `src/core/bootstrap/app.py` (строки 14-30)

```python
# Проблема: импорты после логики
from alembic.config import Config
import alembic.command as command
sys.path = _ORIGINAL_SYS_PATH
from fastapi import FastAPI  # E402
from fastapi.middleware.cors import CORSMiddleware  # E402
```

#### 3. Неиспользуемые импорты (F401) — 73 случая

**Критичные production файлы:**

| Файл | Неиспользуемые импорты |
|------|------------------------|
| `src/apps/market_data/service_layer.py` | `AGGREGATE_VIEW_BY_TIMEFRAME`, `BASE_TIMEFRAME_MINUTES` |
| `src/apps/signals/services.py` | `FinalSignal`, `MarketDecision` |
| `src/apps/patterns/domain/context.py` | `PatternStatistic` |
| `src/apps/market_data/repos.py` | `Select` |
| `src/core/db/session.py` | `Session` |

#### 4. Прочие нарушения

| Нарушение | Файл | Строка |
|-----------|------|--------|
| f-string без плейсхолдеров (F541) | `src/apps/market_data/repos.py` | 226 |
| Переменная не используется (F841) | `src/apps/signals/services.py` | — |

### Рекомендации по исправлению

```bash
# Запуск линтера со статистикой
uv run ruff check --statistics

# Автоматическое исправление простых нарушений
uv run ruff check --fix

# Проверка типов (если используется mypy/pyright)
uv run mypy src/
```

---

## База данных и миграции

### Сильные стороны ✅

| Аспект | Описание |
|--------|----------|
| **TimescaleDB hypertable** | 30-дневные чанки, хеш-партиционирование по `coin_id`, 90-дневная компрессия |
| **История миграций** | 28 миграций с подробным описанием |
| **Soft delete** | Паттерн мягкого удаления с `deleted_at` |
| **Индексы** | Композитные и нисходящие индексы для производительности |

**Пример конфигурации TimescaleDB:**

```sql
-- 30-day chunks, hash partitioning, 90-day compression
SELECT create_hypertable('candles', 'timestamp', chunk_time_interval => INTERVAL '30 days');
SELECT add_retention_policy('candles', INTERVAL '90 days');
```

### Проблемные моменты ⚠️

| Проблема | Риск | Рекомендация |
|----------|------|--------------|
| Нет валидации ограничений БД | Средняя | Добавить CHECK constraints |
| Крупные пакетные операции без транзакций | Высокая | Явное управление транзакциями для `PRICE_HISTORY_UPSERT_BATCH_SIZE = 5000` |
| Нет тестирования отката миграций | Средняя | Добавить тесты на `alembic downgrade` |

### Структура миграций

```
src/migrations/versions/
├── 20260310_000001_initial_schema.py
├── 20260310_000002_observed_assets_and_intervals.py
├── 20260310_000003_coin_sync_backoff.py
├── 20260310_000004_coin_backfill_state.py
├── 20260311_000005_seed_default_assets.py
├── 20260311_000006_coin_metrics.py
├── 20260311_000007_analytics_layer.py
├── 20260311_000008_unify_history_storage.py
├── 20260311_000009_relax_candle_timeframe_constraint.py
├── 20260311_000010_pattern_intelligence_foundation.py
├── 20260311_000011_coin_metrics_regime_details.py
├── 20260311_000012_investment_decisions.py
├── 20260311_000013_liquidity_risk_engine.py
├── 20260311_000014_self_evolving_strategy_engine.py
├── 20260311_000015_data_architecture_foundation.py
├── 20260311_000016_smart_market_layers.py
├── 20260311_000017_pattern_success_engine.py
├── 20260311_000018_signal_fusion_engine.py
├── 20260311_000019_portfolio_engine.py
├── 20260311_000020_cross_market_prediction.py
├── 20260312_000021_anomaly_detection_subsystem.py
├── 20260312_000022_news_source_plugins.py
├── 20260312_000023_news_normalization_pipeline.py
├── 20260312_000024_market_structure_snapshots.py
├── 20260312_000025_market_structure_sources.py
├── 20260312_000026_market_structure_source_health.py
├── 20260312_000027_market_structure_source_resilience.py
└── 20260312_000028_hypothesis_engine.py
```

---

## Тестирование

### Сильные стороны ✅

| Аспект | Описание |
|--------|----------|
| **Структура тестов** | Domain-scoped layout: `tests/apps/`, `tests/runtime/`, `tests/core/` |
| **Factory pattern** | `tests/factories/` для тестовых данных |
| **Изоляция** | Фикстуры для Redis streams, очистки БД, состояния портфеля |
| **Event-driven тесты** | Тесты Redis Stream consumer groups |

### Проблемные моменты ⚠️

| Проблема | Файлы | Рекомендация |
|----------|-------|--------------|
| Дублирование фикстур очистки | `tests/conftest.py`, `tests/apps/conftest.py` | Вынести в базовый класс/утилиту |
| Нет тестов производительности | — | Добавить pytest-benchmark |
| Нет интеграционных тестов API | — | Добавить тесты внешних API клиентов |

### Покрытие тестами

```
tests/
├── apps/
│   ├── anomalies/          # 6 тестов
│   ├── cross_market/       # 8 тестов
│   ├── hypothesis_engine/  # 6 тестов
│   ├── indicators/         # 12 тестов
│   ├── market_data/        # 15 тестов
│   ├── market_structure/   # 8 тестов
│   ├── news/               # 6 тестов
│   ├── patterns/           # 20 тестов
│   ├── portfolio/          # 12 тестов
│   ├── predictions/        # 8 тестов
│   ├── signals/            # 15 тестов
│   └── system/             # 4 тестов
├── runtime/
│   ├── orchestration/      # 5 тестов
│   ├── scheduler/          # 4 тестов
│   └── streams/            # 8 тестов
├── core/
│   ├── db/                 # 3 тестов
│   └── settings/           # 2 тестов
└── factories/              # Factory classes
```

---

## Runtime и оркестрация

### Сильные стороны ✅

| Компонент | Описание |
|-----------|----------|
| **TaskIQ + Redis Stream** | Фоновые задачи с consumer groups |
| **Изоляция воркеров** | indicator_workers, pattern_workers, portfolio_workers и т.д. |
| **Graceful shutdown** | События и очистка процессов |
| **Distributed locks** | Redis для координации задач |

### Проблемные моменты ⚠️

| Проблема | Риск | Рекомендация |
|----------|------|--------------|
| Нет retry/backoff в TaskIQ | Высокая | Добавить декораторы с retry logic |
| Захардкоженные интервалы | Средняя | Вынести в конфигурацию |
| Нет dead letter queue | Высокая | Реализовать DLQ для неудачных событий |
| Thread-based publisher | Средняя | Рассмотреть async альтернативу |

### Архитектура воркеров

```
Redis Streams Consumer Groups:
├── indicator_workers
├── analysis_scheduler_workers
├── pattern_workers
├── regime_workers
├── cross_market_workers
├── decision_workers
├── signal_fusion_workers
└── portfolio_workers
```

---

## API дизайн

### Сильные стороны ✅

| Аспект | Описание |
|--------|----------|
| **RESTful паттерны** | Согласованные endpoints во всех apps |
| **Async endpoints** | Повсеместно |
| **HTTP status codes** | Правильное использование 200/201/204/400/404/409 |
| **OpenAPI documentation** | Теги и описания |

### Проблемные моменты ⚠️

| Проблема | Риск | Рекомендация |
|----------|------|--------------|
| Нет версионирования API | Высокая | Добавить `/api/v1/` префикс |
| Нет rate limiting | Высокая | Интегрировать slowapi |
| Нет валидации размера | Средняя | Добавить middleware для request/response limits |
| Несогласованные ошибки | Низкая | Унифицировать формат ошибок |

### Доступные endpoints

```
Market Data:
├── GET    /coins
├── POST   /coins
├── DELETE /coins/{symbol}
├── POST   /coins/{symbol}/jobs/run
├── GET    /coins/{symbol}/history
└── POST   /coins/{symbol}/history

Signals:
├── GET    /signals
├── GET    /signals/top
└── GET    /coins/{symbol}/signals

Portfolio:
├── GET    /portfolio/positions
├── GET    /portfolio/actions
└── GET    /portfolio/state

Market Flow:
├── GET    /market/flow
└── GET    /predictions
```

---

## Безопасность

### Критические проблемы 🔴

| Проблема | Риск | Рекомендация |
|----------|------|--------------|
| Нет аутентификации/авторизации | Критический | JWT или API key authentication |
| CORS разрешает все origins | Высокий | Ограничить whitelist |
| API-ключи в env без шифрования | Высокий | Использовать secrets manager |
| Нет санитизации входов | Высокий | Валидация и санитизация всех входов |

### Рекомендуемый стек безопасности

```yaml
Authentication:
  - JWT tokens (PyJWT)
  - API keys для сервисов
  - OAuth2 для пользователей

Authorization:
  - Role-based access control (RBAC)
  - Permission decorators

Rate Limiting:
  - slowapi (Redis-backed)
  - Tiered limits по пользователям

Input Validation:
  - Pydantic validators
  - Custom sanitizers
  - Size limits
```

---

## Производительность

### Сильные стороны ✅

| Оптимизация | Описание |
|-------------|----------|
| **Redis caching** | Кеширование режимов, решений, состояния портфеля |
| **Connection pooling** | SQLAlchemy pool |
| **Batch operations** | Пакетные upsert для свечей |

### Проблемные моменты ⚠️

| Проблема | Риск | Рекомендация |
|----------|------|--------------|
| N+1 запросы | Высокая | Добавить eager loading (selectinload, joinedload) |
| Нет timeout запросов | Средняя | Добавить execution_timeout в SQLAlchemy |
| Нет retry с backoff | Средняя | Экспоненциальный backoff для БД |
| Sync миграции на старте | Низкая | Вынести в init container |

### Рекомендации по оптимизации

```python
# Eager loading пример
from sqlalchemy.orm import selectinload

stmt = select(Coin).options(
    selectinload(Coin.metrics),
    selectinload(Coin.sector),
    selectinload(Coin.signals).limit(10),
)
```

---

## Наблюдаемость

### Отсутствует 🔴

| Компонент | Рекомендация |
|-----------|--------------|
| **Структурированное логирование** | structlog или loguru |
| **Метрики/мониторинг** | Prometheus + Grafana |
| **Распределённая трассировка** | OpenTelemetry |
| **Health checks** | Расширенный `/health` endpoint |
| **Алертинг** | PagerDuty/Slack интеграция |

### Рекомендуемая конфигурация логирования

```python
# structlog конфигурация
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
```

---

## Docker и развёртывание

### Сильные стороны ✅

| Аспект | Описание |
|--------|----------|
| **Multi-service** | docker-compose с db, redis, backend, frontend |
| **Health checks** | Для PostgreSQL и Redis |
| **Volumes** | Персистентность данных |

### Проблемные моменты ⚠️

| Проблема | Риск | Рекомендация |
|----------|------|--------------|
| Нет production конфигурации | Высокая | Добавить Kubernetes/Helm manifests |
| Нет secrets management | Высокая | Docker secrets или HashiCorp Vault |
| Нет горизонтального масштабирования | Средняя | Kubernetes HPA config |
| Single-replica дизайн | Средняя | Stateless архитектура для backend |

### docker-compose.yml анализ

```yaml
services:
  db:       # TimescaleDB, port 55432
  redis:    # Redis 7, port 56379
  backend:  # FastAPI, port 8000
  frontend: # Vue 3, port 3000
```

**Отсутствует:**
- Reverse proxy (nginx/traefik)
- SSL/TLS termination
- Log aggregation
- Monitoring stack

---

## Приоритетные рекомендации

### Немедленно (P0) — 1-2 недели

| # | Задача | Файлы | Сложность |
|---|--------|-------|-----------|
| 1 | Исправить F822 undefined names | `indicators/analytics.py`, `signals/services.py` | Низкая |
| 2 | Добавить authentication | `core/auth/`, middleware | Высокая |
| 3 | Реализовать rate limiting | middleware, slowapi | Средняя |
| 4 | Исправить E402 imports | `core/bootstrap/app.py` | Низкая |
| 5 | Удалить 73 unused imports | Все файлы | Низкая |

### Краткосрочно (P1) — 2-4 недели

| # | Задача | Сложность |
|---|--------|-----------|
| 6 | Структурированное логирование (structlog) | Средняя |
| 7 | Circuit breakers для внешних API | Высокая |
| 8 | Query timeouts + retry с backoff | Средняя |
| 9 | Dead letter queue для событий | Высокая |
| 10 | API versioning стратегия | Средняя |

### Среднесрочно (P2) — 1-3 месяца

| # | Задача | Сложность |
|---|--------|-----------|
| 11 | Monitoring/metrics (Prometheus) | Высокая |
| 12 | Load testing suite | Средняя |
| 13 | Реальные биржевые API | Высокая |
| 14 | Distributed tracing (OpenTelemetry) | Высокая |
| 15 | Request/response size limits | Низкая |

---

## Чеклист для продакшена

### Безопасность
- [ ] JWT authentication
- [ ] Rate limiting
- [ ] CORS whitelist
- [ ] Input sanitization
- [ ] Secrets management

### Надёжность
- [ ] Health checks
- [ ] Circuit breakers
- [ ] Retry logic
- [ ] Dead letter queue
- [ ] Graceful shutdown

### Наблюдаемость
- [ ] Structured logging
- [ ] Metrics collection
- [ ] Distributed tracing
- [ ] Alerting rules
- [ ] Dashboard (Grafana)

### Развёртывание
- [ ] Kubernetes manifests
- [ ] CI/CD pipeline
- [ ] Database migrations automation
- [ ] Rollback strategy
- [ ] Backup/restore procedure

---

## Заключение

IRIS backend — это зрелая кодовая база с отличной архитектурой для обработки сложных финансовых данных. Приоритетные области для улучшения: **безопасность, наблюдаемость и операционная готовность**.

**Следующие шаги:**
1. Исправить критические linting нарушения (P0)
2. Добавить authentication layer (P0)
3. Внедрить структурированное логирование (P1)
4. Подготовить production deployment конфигурацию (P2)

---

*Документ сгенерирован: 12 марта 2026*  
*Инструменты анализа: ruff, pytest, ручной аудит кода*
