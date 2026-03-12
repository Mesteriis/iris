# IRIS — Бизнес-ревью архитектуры и взаимодействия доменов

**Дата:** 12 марта 2026  
**Тип документа:** Архитектурный анализ  
**Аудитория:** Технические лиды, архитекторы, продукт-менеджеры

---

## Содержание

1. [Обзор бизнес-архитектуры](#обзор-бизнес-архитектуры)
2. [Доменная карта](#доменная-карта)
3. [Взаимодействие доменов](#взаимодействие-доменов)
4. [Потоки данных](#потоки-данных)
5. [Бизнес-возможности](#бизнес-возможности)
6. [Технический долг и риски](#технический-долг-и-риски)
7. [Рекомендации по развитию](#рекомендации-по-развитию)

---

## 1. Обзор бизнес-архитектуры

### 1.1 Назначение системы

**IRIS** — это сервис рыночной аналитики, который предоставляет:

- **Анализ рыночных данных** в реальном времени
- **Обнаружение паттернов** на исторических данных
- **Генерацию торговых сигналов** с оценкой уверенности
- **Управление портфелем** с автоматическим расчётом позиций
- **Кросс-маркет аналитику** с корреляциями между активами

### 1.2 Ценностное предложение

| Для кого | Ценность |
|----------|----------|
| **Трейдеры** | Автоматическое обнаружение паттернов и сигналов |
| **Инвесторы** | Управление портфелем с риск-менеджментом |
| **Аналитики** | Исторические данные и бэктестинг стратегий |
| **Разработчики** | API для интеграции с внешними системами |

### 1.3 Архитектурный стиль

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Vue 3)                        │
│   Dashboard │ Pattern Map │ Portfolio Radar │ Decision Map │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  API Gateway (FastAPI)                      │
│              /api/v1/* REST endpoints                       │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐  ┌────────────────┐  ┌───────────────┐
│   Commands    │  │   Queries      │  │   Events      │
│   (Write)     │  │   (Read)       │  │  (Publish)    │
└───────────────┘  └────────────────┘  └───────────────┘
        │                   │                   │
        ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                   Domain Services                           │
│  market_data │ indicators │ patterns │ signals │ portfolio │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐  ┌────────────────┐  ┌───────────────┐
│  TimescaleDB  │  │  Redis Cache   │  │ Redis Streams │
│  (Candles)    │  │  (State)       │  │   (Events)    │
└───────────────┘  └────────────────┘  └───────────────┘
```

---

## 2. Доменная карта

### 2.1 Основные домены

```
┌────────────────────────────────────────────────────────────────────┐
│                         CORE DOMAINS                               │
├────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │ Market Data  │  │  Indicators  │  │   Patterns   │             │
│  │    (ядро)    │  │   (анализ)   │  │  (распознав.)│             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   Signals    │  │   Portfolio  │  │    News      │             │
│  │  (сигналы)   │  │ (портфель)   │  │  (новости)   │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│                      SUPPORTING DOMAINS                            │
├────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │Cross-Market  │  │  Anomalies   │  │  Predictions │             │
│  │(корреляции)  │  │ (аномалии)   │  │(предсказания)│             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │  Hypothesis  │  │    Market    │  │   System     │             │
│  │   (гипотезы) │  │  Structure   │  │  (системный) │             │
│  │              │  │ (структура)  │  │              │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 Детальная карта доменов

#### **Market Data (Ядро)**

| Аспект | Описание |
|--------|----------|
| **Ответственность** | Приём, хранение и предоставление рыночных данных (OHLCV) |
| **Ключевые сущности** | `Coin`, `Candle`, `PriceHistory` |
| **Внешние зависимости** | Polygon, TwelveData, AlphaVantage, Binance, Kraken |
| **API** | `/coins`, `/coins/{symbol}/history` |
| **События** | `candle_inserted`, `candle_closed`, `coin_history_loaded` |

**Бизнес-правила:**
- Поддержка множественных источников данных (carousel pattern)
- Автоматический failover между провайдерами
- Backfill исторических данных при добавлении нового актива
- Инкрементальное обновление последних данных

---

#### **Indicators (Аналитика)**

| Аспект | Описание |
|--------|----------|
| **Ответственность** | Вычисление технических индикаторов и метрик |
| **Ключевые сущности** | `IndicatorCache`, `CoinMetrics`, `FeatureSnapshot` |
| **Индикаторы** | SMA, EMA, MACD, RSI, ATR, Bollinger Bands, ADX |
| **События** | `indicator_updated`, `market_regime_changed` |

**Бизнес-правила:**
- Кэширование рассчитанных индикаторов
- Пересчёт при новых свечах
- Определение market regime (trend, sideways, volatility)

---

#### **Patterns (Распознавание)**

| Аспект | Описание |
|--------|----------|
| **Ответственность** | Обнаружение графических паттернов на ценовых данных |
| **Ключевые сущности** | `PatternRegistry`, `PatternStatistic`, `MarketCycle` |
| **Детекторы** | 87 паттернов (structural, continuation, momentum, volatility, volume) |
| **События** | `pattern_detected`, `pattern_cluster_detected` |

**Бизнес-правила:**
- Incremental detection на новых свечах
- Bootstrap scan на исторических данных
- Success Engine с валидацией по историческим результатам
- Lifecycle management (ACTIVE, EXPERIMENTAL, COOLDOWN, DISABLED)

---

#### **Signals (Сигналы)**

| Аспект | Описание |
|--------|----------|
| **Ответственность** | Генерация и хранение торговых сигналов |
| **Ключевые сущности** | `Signal`, `SignalHistory`, `FinalSignal` |
| **Типы сигналов** | Pattern signals, Cluster signals, Hierarchy signals |
| **События** | `signal_created`, `signal_history_evaluated` |

**Бизнес-правила:**
- Приоритизация сигналов по confidence и context
- Оценка результатов через 24h/72h
- Риск-адаптивная корректировка

---

#### **Portfolio (Портфель)**

| Аспект | Описание |
|--------|----------|
| **Ответственность** | Управление позициями и капиталом |
| **Ключевые сущности** | `PortfolioPosition`, `PortfolioBalance`, `PortfolioAction` |
| **Интеграции** | Bybit, Binance (плагин-архитектура) |
| **События** | `portfolio_balance_updated`, `portfolio_position_changed` |

**Бизнес-правила:**
- Max position size: 5% капитала
- Max positions: 20
- Max sector exposure: 25%
- ATR-based stop loss / take profit

---

#### **News (Новости)**

| Аспект | Описание |
|--------|----------|
| **Ответственность** | Сбор и нормализация новостей |
| **Ключевые сущности** | `NewsSource`, `NewsItem`, `NewsItemLink` |
| **Источники** | X (Twitter), Telegram, Discord |
| **События** | `news_item_ingested` |

**Бизнес-правила:**
- Plugin-based архитектура источников
- Корреляция новостей с символами
- Влияние на fusion decisions

---

#### **Cross-Market (Кросс-маркет)**

| Аспект | Описание |
|--------|----------|
| **Ответственность** | Корреляции между активами, секторный анализ |
| **Ключевые сущности** | `CoinRelation`, `Sector`, `SectorMetric` |
| **Метрики** | Lag correlation, sector strength, capital flow |
| **События** | `market_leader_detected`, `sector_rotation_detected` |

**Бизнес-правила:**
- Rolling correlation с lag detection
- Sector momentum tracking
- Leader → follower influence

---

#### **Predictions (Предсказания)**

| Аспект | Описание |
|--------|----------|
| **Ответственность** | Кросс-маркет предсказания и оценка результатов |
| **Ключевые сущности** | `MarketPrediction`, `PredictionResult` |
| **События** | `prediction_evaluated` |

**Бизнес-правила:**
- Prediction на основе leader-follower relations
- Оценка accuracy и feedback в confidence

---

#### **Anomalies (Аномалии)**

| Аспект | Описание |
|--------|----------|
| **Ответственность** | Обнаружение аномалий рынка |
| **Ключевые сущности** | `MarketAnomaly`, `MarketAnomalyPolicy` |
| **Детекторы** | Price, Volume, Volatility, Correlation breakdown |
| **События** | `anomaly_detected` |

**Бизнес-правила:**
- Fast-path детекторы (price/volume/volatility)
- Slow-path детекторы (sector/market-structure)
- Cooldown и confirmation policies

---

#### **Market Structure (Структура рынка)**

| Аспект | Описание |
|--------|----------|
| **Ответственность** | Внешние данные о ликвидациях, funding, open interest |
| **Ключевые сущности** | `MarketStructureSnapshot`, `MarketStructureSource` |
| **Источники** | Liqscope, Coinglass, Hyblock, Coinalyze |
| **События** | `market_structure_snapshot_ingested` |

**Бизнес-правила:**
- Webhook и polling источники
- Source health monitoring
- Quarantine для неудачных источников

---

#### **Hypothesis Engine (Гипотезы)**

| Аспект | Описание |
|--------|----------|
| **Ответственность** | AI-гипотезы на основе сигналов |
| **Ключевые сущности** | `AIHypothesis`, `AIHypothesisEval`, `AIPrompt` |
| **Интеграции** | OpenAI API, Local LLM (Ollama) |
| **События** | `hypothesis_evaluated` |

**Бизнес-правила:**
- Генерация гипотез из сигналов
- Оценка и weighting гипотез
- Feedback loop для обучения

---

### 2.3 Матрица доменов

| Домен | Тип | Критичность | Зрелость | Владелец |
|-------|-----|-------------|----------|----------|
| Market Data | Core | Критический | Высокая | Backend team |
| Indicators | Core | Критический | Высокая | Backend team |
| Patterns | Core | Критический | Средняя | Backend team |
| Signals | Core | Критический | Высокая | Backend team |
| Portfolio | Core | Высокий | Средняя | Backend team |
| News | Supporting | Средний | Низкая | Backend team |
| Cross-Market | Supporting | Средний | Средняя | Backend team |
| Predictions | Supporting | Средний | Низкая | Backend team |
| Anomalies | Supporting | Низкий | Низкая | Backend team |
| Market Structure | Supporting | Средний | Низкая | Backend team |
| Hypothesis | Supporting | Низкий | Низкая | Backend team |

---

## 3. Взаимодействие доменов

### 3.1 Event Storming — основной поток

```
┌─────────────┐
│  External   │
│   Market    │
│   Sources   │
└──────┬──────┘
       │ fetch_history_window()
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         MARKET DATA                                 │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐               │
│  │   Polling   │──▶│   Candles   │──▶│   Events    │               │
│  │   Job       │   │   (DB)      │   │  (Publish)  │               │
│  └─────────────┘   └─────────────┘   └─────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
       │
       │ candle_closed
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         INDICATORS                                  │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐               │
│  │  Compute    │──▶│  Metrics    │──▶│   Events    │               │
│  │ Indicators  │   │  (Update)   │   │  (Publish)  │               │
│  └─────────────┘   └─────────────┘   └─────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
       │
       │ indicator_updated
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      ANALYSIS SCHEDULER                             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐               │
│  │  Activity   │──▶│   Bucket    │──▶│   Events    │               │
│  │   Score     │   │  (HOT/WARM) │   │  (Publish)  │               │
│  └─────────────┘   └─────────────┘   └─────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
       │
       │ analysis_requested
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          PATTERNS                                   │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐               │
│  │  Detect     │──▶│  Success    │──▶│   Signals   │               │
│  │  Patterns   │   │  Validate   │   │  (Persist)  │               │
│  └─────────────┘   └─────────────┘   └─────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
       │
       │ pattern_detected
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          SIGNALS                                    │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐               │
│  │   Context   │──▶│  Priority   │──▶│   Events    │               │
│  │  Enrich     │   │   Score     │   │  (Publish)  │               │
│  └─────────────┘   └─────────────┘   └─────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
       │
       │ signal_created
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       SIGNAL FUSION                                 │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐               │
│  │  Aggregate  │──▶│   Decision  │──▶│   Events    │               │
│  │  Signals    │   │   (BUY/SELL)│   │  (Publish)  │               │
│  └─────────────┘   └─────────────┘   └─────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
       │
       │ decision_generated
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         PORTFOLIO                                   │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐               │
│  │   Position  │──▶│   Action    │──▶│   Events    │               │
│  │   Sizing    │   │  (Execute)  │   │  (Publish)  │               │
│  └─────────────┘   └─────────────┘   └─────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Матрица взаимодействий

| От | К | Тип | Событие/Вызов | Частота |
|----|---|-----|---------------|---------|
| Market Data | Indicators | Event | `candle_closed` | Каждые 15м |
| Indicators | Analysis Scheduler | Event | `indicator_updated` | Каждые 15м |
| Analysis Scheduler | Patterns | Event | `analysis_requested` | По активности |
| Patterns | Signals | Event | `pattern_detected` | По обнаружению |
| Signals | Signal Fusion | Event | `signal_created` | По сигналу |
| Signal Fusion | Portfolio | Event | `decision_generated` | По решению |
| Cross-Market | Signal Fusion | Query | Correlation data | Каждые 15м |
| News | Signal Fusion | Event | `news_item_ingested` | По новостям |
| Predictions | Cross-Market | Feedback | `prediction_evaluated` | Каждые 10м |
| Anomalies | Market Structure | Event | `anomaly_detected` | По аномалиям |

### 3.3 Зависимости доменов

```
                    ┌───────────────┐
                    │  Market Data  │
                    │     (ядро)    │
                    └───────┬───────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
            ▼               ▼               ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │  Indicators  │ │   Patterns   │ │    News      │
    └───────┬──────┘ └───────┬──────┘ └───────┬──────┘
            │               │               │
            └───────────────┼───────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │   Signals    │
                    └───────┬──────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
            ▼               ▼               ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │    Cross     │ │  Signal      │ │  Anomalies   │
    │    Market    │ │   Fusion     │ │              │
    └───────┬──────┘ └───────┬──────┘ └───────┬──────┘
            │               │               │
            └───────────────┼───────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │  Portfolio   │
                    └──────────────┘
```

---

## 4. Потоки данных

### 4.1 Основной поток: Свеча → Решение

```
1. [External] → Market Data
   - Fetch OHLCV from Binance/Polygon/etc.
   - Upsert into candles table
   
2. Market Data → Redis Streams
   - Publish: candle_closed {coin_id, timeframe, timestamp}
   
3. Redis Streams → Indicators
   - Consume: candle_closed
   - Compute: SMA, EMA, MACD, RSI, ATR, Bollinger
   - Update: indicator_cache, coin_metrics
   - Publish: indicator_updated
   
4. Redis Streams → Analysis Scheduler
   - Consume: indicator_updated
   - Calculate: activity_score, activity_bucket
   - Decide: HOT/WARM/COLD/DEAD
   - Publish: analysis_requested (если HOT)
   
5. Redis Streams → Patterns
   - Consume: analysis_requested
   - Load: last 200 candles
   - Run: 87 pattern detectors
   - Validate: Success Engine (historical success rate)
   - Persist: signals (pattern_detected)
   - Publish: pattern_detected
   
6. Redis Streams → Signals
   - Consume: pattern_detected
   - Enrich: context_score, regime_alignment
   - Calculate: priority_score
   - Persist: signals
   - Publish: signal_created
   
7. Redis Streams → Signal Fusion
   - Consume: signal_created (last 1-3 signals)
   - Aggregate: weighted by confidence, history, regime
   - Decide: BUY/SELL/HOLD/WATCH
   - Persist: market_decisions
   - Publish: decision_generated
   
8. Redis Streams → Portfolio
   - Consume: decision_generated
   - Calculate: position_size (confidence, regime, volatility)
   - Check: portfolio limits (max 20 positions, 5% each)
   - Execute: OPEN_POSITION / CLOSE_POSITION / etc.
   - Persist: portfolio_positions, portfolio_actions
   - Publish: portfolio_position_changed
```

### 4.2 Параллельные потоки

#### **Cross-Market Intelligence**

```
1. Redis Streams → Cross-Market
   - Consume: candle_closed, indicator_updated
   - Calculate: rolling correlation with lag
   - Detect: leader → follower relations
   - Persist: coin_relations
   - Publish: market_leader_detected
   
2. Cross-Market → Signal Fusion
   - Query: correlation data for decision weighting
   
3. Cross-Market → Predictions
   - Generate: market predictions (BTC breakout → ETH follow-through)
   - Persist: market_predictions
```

#### **News Processing**

```
1. [External] → News
   - Poll: X, Telegram, Discord
   - Normalize: news_items
   - Correlate: with coin symbols
   - Persist: news_items, news_item_links
   - Publish: news_item_ingested
   
2. News → Signal Fusion
   - Consume: news_item_ingested
   - Weight: decision confidence based on news correlation
```

#### **Anomaly Detection**

```
1. Redis Streams → Anomalies
   - Consume: candle_closed
   - Run: fast-path detectors (price/volume/volatility)
   - Run: slow-path detectors (sector/correlation)
   - Score: weighted anomaly score
   - Persist: market_anomalies
   - Publish: anomaly_detected
   
2. Anomalies → Market Structure
   - Trigger: market_structure scan for high-severity anomalies
```

#### **Market Structure**

```
1. [External] → Market Structure
   - Poll/Webhook: Liqscope, Coinglass, Hyblock
   - Normalize: liquidation, funding, open interest data
   - Persist: market_structure_snapshots
   - Publish: market_structure_snapshot_ingested
   
2. Market Structure → All Domains
   - Provide: context for patterns, signals, decisions
```

### 4.3 Хранилища данных

```
┌─────────────────────────────────────────────────────────────────┐
│                         TimescaleDB                             │
├─────────────────────────────────────────────────────────────────┤
│  candles              (OHLCV, 30-day chunks, 90-day retention) │
│  indicator_cache      (computed indicators per coin/timeframe) │
│  coin_metrics         (current market state, regime)           │
│  signals              (detected patterns, confidence)          │
│  signal_history       (evaluated outcomes, 24h/72h returns)    │
│  market_decisions     (fused BUY/SELL/HOLD/WATCH)              │
│  portfolio_positions  (open positions, stops, P/L)             │
│  coin_relations       (leader-follower correlations)           │
│  pattern_statistics   (success rates per pattern)              │
│  ... (50+ tables)                                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                          Redis Cache                            │
├─────────────────────────────────────────────────────────────────┤
│  iris:regime:{coin_id}:{timeframe}     → market regime         │
│  iris:decision:{coin_id}:{timeframe}   → fused decision        │
│  iris:portfolio:state                  → portfolio summary     │
│  iris:portfolio:balances               → exchange balances     │
│  iris:correlation:{leader}:{follower}  → correlation data      │
│  iris:prediction:{id}                  → prediction state      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       Redis Streams                             │
├─────────────────────────────────────────────────────────────────┤
│  iris_events (main event bus)                                   │
│    - candle_closed, indicator_updated, pattern_detected         │
│    - signal_created, decision_generated, anomaly_detected       │
│                                                                 │
│  Consumer Groups:                                               │
│    - indicator_workers, pattern_workers, signal_workers         │
│    - portfolio_workers, cross_market_workers, anomaly_workers   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Бизнес-возможности

### 5.1 Текущие возможности

| Возможность | Статус | Зрелость | Ценность |
|-------------|--------|----------|----------|
| **Мониторинг рынка** | ✅ Готово | Высокая | Высокая |
| **Обнаружение паттернов** | ✅ Готово | Средняя | Высокая |
| **Торговые сигналы** | ✅ Готово | Высокая | Высокая |
| **Управление портфелем** | ✅ Готово | Средняя | Высокая |
| **Кросс-маркет аналитика** | ✅ Готово | Средняя | Средняя |
| **Новостной анализ** | ✅ Готово | Низкая | Средняя |
| **Предсказания** | 🟡 MVP | Низкая | Средняя |
| **Аномалии** | 🟡 MVP | Низкая | Низкая |
| **AI гипотезы** | 🟡 MVP | Низкая | Низкая |

### 5.2 Будущие возможности

#### **Близкий горизонт (1-3 месяца)**

| Возможность | Описание | Зависимости | Приоритет |
|-------------|----------|-------------|-----------|
| **Production authentication** | JWT/API key auth | Security | P0 |
| **Rate limiting** | API protection | Security | P0 |
| **Real exchange integration** | Bybit/Binance execution | Portfolio | P1 |
| **Backtesting UI** | Historical strategy testing | signal_history | P1 |
| **Alerting system** | Email/SMS/Push notifications | Signals | P1 |

#### **Средний горизонт (3-6 месяцев)**

| Возможность | Описание | Зависимости | Приоритет |
|-------------|----------|-------------|-----------|
| **Mobile app** | iOS/Android приложение | API | P2 |
| **Advanced analytics** | ML-based predictions | Hypothesis Engine | P2 |
| **Social features** | Shared strategies, copy trading | Portfolio | P2 |
| **Multi-language support** | i18n for frontend | Frontend | P3 |

#### **Дальний горизонт (6-12 месяцев)**

| Возможность | Описание | Зависимости | Приоритет |
|-------------|----------|-------------|-----------|
| **Institutional tier** | Multi-user, RBAC, audit | Auth, Security | P2 |
| **White-label API** | Reseller program | API, Billing | P3 |
| **DeFi integration** | DEX, lending protocols | Portfolio | P3 |

### 5.3 Монетизация

| Tier | Цена | Возможности | Целевая аудитория |
|------|------|-------------|-------------------|
| **Free** | $0 | Basic signals, 10 coins, delayed | Beginners |
| **Pro** | $49/mo | All signals, 50 coins, real-time | Active traders |
| **Business** | $199/mo | Portfolio mgmt, API access, alerts | Professional traders |
| **Institutional** | Custom | White-label, SLA, dedicated support | Funds, family offices |

---

## 6. Технический долг и риски

### 6.1 Критические риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| **Нет аутентификации** | Высокая | Критическое | Реализовать JWT auth (P0) |
| **Нет rate limiting** | Высокая | Высокое | Интегрировать slowapi (P0) |
| **Один провайдер данных** | Средняя | Высокое | Расширить carousel (P1) |
| **Нет мониторинга** | Средняя | Высокое | Prometheus + Grafana (P1) |
| **Биржевые заглушки** | Высокая | Среднее | Реализовать Bybit/Binance (P1) |

### 6.2 Архитектурные риски

| Риск | Описание | Влияние |
|------|----------|---------|
| **Смешанные sync/async** | asyncio.run() в sync коде | Блокировки, deadlock risk |
| **Монолитный scheduler** | 12+ задач в одном модуле | Сложность поддержки |
| **Нет версионирования API** | Breaking changes без контроля | Клиентские breaking changes |
| **Hardcoded intervals** | 20+ интервалов в settings | Сложность тюнинга |

### 6.3 Бизнес-риски

| Риск | Описание | Влияние |
|------|----------|---------|
| **Зависимость от API** | Polygon, TwelveData могут изменить pricing | Cost increase |
| **Конкуренция** | TradingView, CoinGlass уже на рынке | Market share risk |
| **Регуляторика** | Crypto regulations меняются | Compliance risk |
| **Нет SLA** | Нет гарантий uptime для клиентов | Customer trust risk |

---

## 7. Рекомендации по развитию

### 7.1 Архитектурные рекомендации

#### **Краткосрочные (1-2 месяца)**

1. **Выделить Event Bus в отдельный сервис**
   ```
   Сейчас: Redis Streams внутри backend
   Будущее: Отдельный event-broker сервис
   ```

2. **Разделить Command и Query стороны (CQRS)**
   ```
   Сейчас: Один FastAPI app для всего
   Будущее: Separate write/read models
   ```

3. **Добавить API Gateway**
   ```
   Сейчас: Прямой доступ к backend
   Будущее: Kong/Traefik с rate limiting, auth
   ```

#### **Среднесрочные (3-6 месяцев)**

4. **Микросервис для Patterns**
   ```
   Сейчас: patterns внутри backend
   Будущее: Отдельный pattern-detection сервис
   ```

5. **Выделить Portfolio в отдельный сервис**
   ```
   Сейчас: portfolio внутри backend
   Будущее: Отдельный portfolio-management сервис
   ```

6. **Добавить Message Queue**
   ```
   Сейчас: Только Redis Streams
   Будущее: Kafka/RabbitMQ для надёжности
   ```

### 7.2 Организационные рекомендации

#### **Команда**

| Роль | Количество | Фокус |
|------|------------|-------|
| Backend Lead | 1 | Архитектура, code review |
| Backend Developer | 2-3 | Domain services, API |
| Frontend Developer | 1-2 | Vue 3 dashboard |
| DevOps Engineer | 0.5 | Infrastructure, CI/CD |
| QA Engineer | 0.5 | Testing, automation |
| Product Manager | 0.5 | Roadmap, priorities |

#### **Процессы**

1. **Еженедельный architecture review**
   - Обсуждение новых фич
   - Review технического долга
   - Планирование рефакторинга

2. **Bi-weekly sprint planning**
   - Приоритизация задач
   - Оценка сложности
   - Распределение ресурсов

3. **Monthly business review**
   - Метрики продукта
   - Обратная связь от пользователей
   - Корректировка roadmap

### 7.3 Дорожная карта

```
Q2 2026 (Апрель-Июнь)
├── P0: Security (auth, rate limiting)
├── P0: Code quality (linting fixes)
├── P1: Real exchange integration
└── P1: Monitoring stack

Q3 2026 (Июль-Сентябрь)
├── P1: Backtesting UI
├── P1: Alerting system
├── P2: Mobile app (MVP)
└── P2: Advanced analytics

Q4 2026 (Октябрь-Декабрь)
├── P2: Social features
├── P2: Institutional tier
├── P3: White-label API
└── P3: DeFi integration
```

### 7.4 Метрики успеха

#### **Технические метрики**

| Метрика | Текущее | Цель Q2 | Цель Q4 |
|---------|---------|---------|---------|
| Uptime | N/A | 99.5% | 99.9% |
| API latency (p95) | N/A | <200ms | <100ms |
| Test coverage | ~60% | 75% | 85% |
| Critical bugs | Unknown | 0 | 0 |

#### **Бизнес-метрики**

| Метрика | Текущее | Цель Q2 | Цель Q4 |
|---------|---------|---------|---------|
| Active users | 0 | 100 | 1000 |
| Paid subscribers | 0 | 10 | 100 |
| MRR | $0 | $500 | $5000 |
| API calls/day | N/A | 10K | 100K |

---

## Заключение

### Сильные стороны архитектуры

1. ✅ **Domain-Driven Design** — чёткое разделение ответственности
2. ✅ **Event-Driven Architecture** — слабосвязанные компоненты
3. ✅ **TimescaleDB** — оптимизированное хранение временных рядов
4. ✅ **Plugin Architecture** — расширяемость для новых источников/бирж
5. ✅ **Comprehensive Testing** — хорошее покрытие тестами

### Области для улучшения

1. 🔴 **Security** — нет аутентификации/авторизации
2. 🔴 **Observability** — нет мониторинга/алертинга
3. 🟡 **Scalability** — нет горизонтального масштабирования
4. 🟡 **Production Readiness** — нет deployment automation

### Итоговая оценка

| Категория | Оценка | Комментарий |
|-----------|--------|-------------|
| **Архитектура** | 8.5/10 | Отличный DDD дизайн |
| **Код** | 7.0/10 | Нужен рефакторинг |
| **Безопасность** | 3.0/10 | Критические пробелы |
| **Надёжность** | 6.5/10 | Нет мониторинга |
| **Масштабируемость** | 6.0/10 | Монолитная структура |
| **Бизнес-ценность** | 8.0/10 | Высокий потенциал |

**Общая оценка: 7.0/10**

---

*Документ сгенерирован: 12 марта 2026*  
*Для вопросов и обсуждений: architecture@iris-project.io*
