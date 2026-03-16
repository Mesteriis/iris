import axios from "axios";
import { computed, ref } from "vue";
import { defineStore } from "pinia";

import {
  buildApiUrl,
  type DashboardAssetStreamEvent,
  type FrontendDashboardSnapshot,
  type DashboardPortfolioStreamEvent,
  irisApi,
  type BacktestSummary,
  type CandleInterval,
  type Coin,
  type CoinBacktests,
  type CoinMarketDecision,
  type CoinRegime,
  type CoinCreatePayload,
  type CoinMetrics,
  type DiscoveredPattern,
  type MarketCycle,
  type MarketFlow,
  type MarketDecision,
  type MarketRadar,
  type PatternDescriptor,
  type PatternFeature,
  type Prediction,
  type PortfolioAction,
  type PortfolioPosition,
  type PortfolioState,
  type PriceHistoryPoint,
  type Sector,
  type SectorMetric,
  type SectorNarrative,
  type Signal,
  type Strategy,
  type StrategyPerformance,
  type SystemStatus,
} from "../services/api";
import { getCoinJobSnapshot } from "../utils/coinJobs";

export const useCoinStore = defineStore("coins", () => {
  const coins = ref<Coin[]>([]);
  const metrics = ref<CoinMetrics[]>([]);
  const signals = ref<Signal[]>([]);
  const topSignals = ref<Signal[]>([]);
  const marketDecisions = ref<MarketDecision[]>([]);
  const patterns = ref<PatternDescriptor[]>([]);
  const strategies = ref<Strategy[]>([]);
  const strategyPerformance = ref<StrategyPerformance[]>([]);
  const topBacktests = ref<BacktestSummary[]>([]);
  const patternFeatures = ref<PatternFeature[]>([]);
  const discoveredPatterns = ref<DiscoveredPattern[]>([]);
  const sectors = ref<Sector[]>([]);
  const sectorMetrics = ref<SectorMetric[]>([]);
  const sectorNarratives = ref<SectorNarrative[]>([]);
  const marketCycles = ref<MarketCycle[]>([]);
  const marketRadar = ref<MarketRadar | null>(null);
  const marketFlow = ref<MarketFlow | null>(null);
  const predictions = ref<Prediction[]>([]);
  const portfolioPositions = ref<PortfolioPosition[]>([]);
  const portfolioActions = ref<PortfolioAction[]>([]);
  const portfolioState = ref<PortfolioState | null>(null);
  const coinBacktests = ref<Record<string, CoinBacktests>>({});
  const coinMarketDecisions = ref<Record<string, CoinMarketDecision>>({});
  const coinPatternHistory = ref<Record<string, Signal[]>>({});
  const coinRegimes = ref<Record<string, CoinRegime>>({});
  const history = ref<PriceHistoryPoint[]>([]);
  const activeSymbol = ref<string>("");
  const activeInterval = ref<CandleInterval>("1d");
  const status = ref<SystemStatus | null>(null);
  const isBootstrapping = ref(false);
  const isHistoryLoading = ref(false);
  const isCreatingCoin = ref(false);
  const dashboardError = ref<string>("");
  const historyError = ref<string>("");
  const createCoinError = ref<string>("");
  const createCoinSuccess = ref<string>("");
  const jobRunError = ref<string>("");
  const jobRunSuccess = ref<string>("");
  const hasDashboardSnapshot = ref(false);
  const runningJobSymbols = ref<Record<string, boolean>>({});
  const lastDashboardRefreshAt = ref<string | null>(null);
  const liveSignalCounts = ref<Record<string, number>>({});
  const liveStreamStatus = ref<"idle" | "connecting" | "connected" | "error">("idle");
  const lastLiveEventAt = ref<string | null>(null);
  let dashboardEventSource: EventSource | null = null;

  const hasHistory = computed(() => history.value.length > 0);
  const enabledCoins = computed(() =>
    [...coins.value]
      .filter((coin) => coin.enabled)
      .sort((left, right) => left.sort_order - right.sort_order || left.symbol.localeCompare(right.symbol)),
  );
  const enabledCoinsCount = computed(() => enabledCoins.value.length);
  const metricsBySymbol = computed(
    () => new Map(metrics.value.map((metric) => [metric.symbol.toUpperCase(), metric])),
  );
  const signalsBySymbol = computed(() => {
    const grouped = new Map<string, Signal[]>();
    for (const signal of signals.value) {
      const symbol = signal.symbol.toUpperCase();
      const bucket = grouped.get(symbol) ?? [];
      bucket.push(signal);
      grouped.set(symbol, bucket);
    }
    return grouped;
  });
  const signalCountsBySymbol = computed(() => {
    const grouped = new Map<string, number>();
    for (const [symbol, items] of signalsBySymbol.value.entries()) {
      grouped.set(symbol, items.length);
    }
    for (const [symbol, count] of Object.entries(liveSignalCounts.value)) {
      grouped.set(symbol, count);
    }
    return grouped;
  });
  const topSignalsBySymbol = computed(() => {
    const grouped = new Map<string, Signal[]>();
    for (const signal of topSignals.value) {
      const symbol = signal.symbol.toUpperCase();
      const bucket = grouped.get(symbol) ?? [];
      bucket.push(signal);
      grouped.set(symbol, bucket);
    }
    return grouped;
  });
  const recentSignals = computed(() =>
    [...signals.value].sort(
      (left, right) =>
        new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
    ),
  );
  const dashboardRows = computed(() =>
    enabledCoins.value
      .map((coin) => {
        const metric = metricsBySymbol.value.get(coin.symbol.toUpperCase());
        const signalCount = signalCountsBySymbol.value.get(coin.symbol.toUpperCase()) ?? 0;
        const topSignal = topSignalsBySymbol.value.get(coin.symbol.toUpperCase())?.[0] ?? null;
        const job = getCoinJobSnapshot(coin);

        return {
          ...coin,
          ...metric,
          job,
          signalCount,
          topSignal,
        };
      })
      .sort((left, right) => {
        const scoreDelta = (right.trend_score ?? -1) - (left.trend_score ?? -1);
        if (scoreDelta !== 0) {
          return scoreDelta;
        }
        return left.sort_order - right.sort_order;
      }),
  );
  const activeCoin = computed(() =>
    coins.value.find((coin) => coin.symbol === activeSymbol.value) ?? null,
  );
  const activeMetrics = computed(() => metricsBySymbol.value.get(activeSymbol.value) ?? null);
  const activeSignals = computed(
    () => signalsBySymbol.value.get(activeSymbol.value)?.slice(0, 12) ?? [],
  );
  const activePatternSignals = computed(() => coinPatternHistory.value[activeSymbol.value] ?? []);
  const activeBacktests = computed(() => coinBacktests.value[activeSymbol.value]?.items ?? []);
  const activeMarketDecision = computed(() => coinMarketDecisions.value[activeSymbol.value] ?? null);
  const activeRegime = computed(() => coinRegimes.value[activeSymbol.value] ?? null);
  const activeCycles = computed(() =>
    marketCycles.value.filter((item) => item.symbol.toUpperCase() === activeSymbol.value),
  );
  const topSectorMetrics = computed(() => sectorMetrics.value.slice(0, 6));
  const hotRadarCoins = computed(() => marketRadar.value?.hot_coins ?? []);
  const emergingRadarCoins = computed(() => marketRadar.value?.emerging_coins ?? []);
  const regimeChangeRadar = computed(() => marketRadar.value?.regime_changes ?? []);
  const volatilitySpikeRadar = computed(() => marketRadar.value?.volatility_spikes ?? []);
  const marketFlowLeaders = computed(() => marketFlow.value?.leaders ?? []);
  const marketFlowRelations = computed(() => marketFlow.value?.relations ?? []);
  const marketFlowSectors = computed(() => marketFlow.value?.sectors ?? []);
  const marketFlowRotations = computed(() => marketFlow.value?.rotations ?? []);
  const predictionJournal = computed(() => predictions.value.slice(0, 12));
  const activeCrossMarketRelations = computed(() =>
    marketFlowRelations.value.filter(
      (item) =>
        item.leader_symbol.toUpperCase() === activeSymbol.value ||
        item.follower_symbol.toUpperCase() === activeSymbol.value,
    ),
  );
  const activePredictionJournal = computed(() =>
    predictions.value.filter(
      (item) =>
        item.leader_symbol.toUpperCase() === activeSymbol.value ||
        item.target_symbol.toUpperCase() === activeSymbol.value,
    ),
  );
  const enabledPatternFeatures = computed(() => patternFeatures.value.filter((item) => item.enabled));
  const topStrategies = computed(() => strategyPerformance.value.slice(0, 6));
  const topMarketDecisionRadar = computed(() => marketDecisions.value.slice(0, 8));
  const openPortfolioPositions = computed(() => portfolioPositions.value.filter((item) => item.status !== "closed"));
  const topPortfolioPositions = computed(() => openPortfolioPositions.value.slice(0, 8));
  const latestPortfolioActions = computed(() => portfolioActions.value.slice(0, 8));
  const portfolioExposure = computed(() => {
    if (!portfolioState.value || portfolioState.value.total_capital <= 0) {
      return 0;
    }
    return (portfolioState.value.allocated_capital / portfolioState.value.total_capital) * 100;
  });
  const portfolioPnl = computed(() =>
    openPortfolioPositions.value.reduce((total, item) => total + (item.unrealized_pnl ?? 0), 0),
  );
  const portfolioRiskBudget = computed(() =>
    openPortfolioPositions.value.reduce(
      (total, item) => total + ((item.risk_to_stop ?? 0) * (item.position_value ?? 0)),
      0,
    ),
  );
  const portfolioWatchRadar = computed(() =>
    openPortfolioPositions.value
      .map((item) => ({
        symbol: item.symbol,
        sourceExchange: item.source_exchange,
        regime: item.regime,
        latestDecision: item.latest_decision,
        latestDecisionConfidence: item.latest_decision_confidence,
        positionValue: item.position_value,
        unrealizedPnl: item.unrealized_pnl,
        riskToStop: item.risk_to_stop,
      }))
      .sort((left, right) => right.positionValue - left.positionValue),
  );
  const activePatternsCount = computed(() =>
    patterns.value.filter((pattern) => pattern.enabled && pattern.lifecycle_state !== "DISABLED").length,
  );
  const disabledPatternsCount = computed(() =>
    patterns.value.filter((pattern) => !pattern.enabled || pattern.lifecycle_state === "DISABLED").length,
  );
  const patternHealthRows = computed(() =>
    patterns.value
      .map((pattern) => {
        const globalStats = pattern.statistics
          .filter((item) => item.market_regime === "all")
          .sort((left, right) => right.total_signals - left.total_signals || right.success_rate - left.success_rate);
        const regimeStats = pattern.statistics
          .filter((item) => item.market_regime !== "all")
          .sort((left, right) => right.success_rate - left.success_rate || right.total_signals - left.total_signals);
        const primary = globalStats[0] ?? regimeStats[0] ?? null;
        return {
          slug: pattern.slug,
          category: pattern.category,
          lifecycleState: pattern.lifecycle_state,
          enabled: pattern.enabled,
          totalSignals: primary?.total_signals ?? 0,
          successRate: primary?.success_rate ?? 0,
          avgReturn: primary?.avg_return ?? 0,
          regimeCount: regimeStats.length,
          bestRegime: regimeStats[0]?.market_regime ?? null,
          bestRegimeSuccess: regimeStats[0]?.success_rate ?? null,
          hottestTemperature:
            pattern.statistics.length > 0
              ? Math.max(...pattern.statistics.map((item) => item.temperature))
              : 0,
        };
      })
      .sort((left, right) => right.successRate - left.successRate || right.totalSignals - left.totalSignals),
  );
  const patternRegimeEfficiency = computed(() =>
    patterns.value
      .flatMap((pattern) =>
        pattern.statistics
          .filter((item) => item.market_regime !== "all" && item.total_signals > 0)
          .map((item) => ({
            slug: pattern.slug,
            market_regime: item.market_regime,
            success_rate: item.success_rate,
            total_signals: item.total_signals,
            enabled: item.enabled,
          })),
      )
      .sort((left, right) => right.success_rate - left.success_rate || right.total_signals - left.total_signals)
      .slice(0, 10),
  );
  const bullishShare = computed(() => {
    if (metrics.value.length === 0) {
      return 0;
    }

    const bullish = metrics.value.filter((metric) => metric.trend === "bullish").length;
    return Math.round((bullish / metrics.value.length) * 100);
  });
  const statusTone = computed(() => {
    if (status.value?.status === "ok" && status.value.taskiq_running) {
      return "ok";
    }

    if (isBootstrapping.value) {
      return "syncing";
    }

    return "down";
  });
  const sourceStatusRows = computed(() =>
    [...(status.value?.sources ?? [])].sort((left, right) => {
      if (left.rate_limited !== right.rate_limited) {
        return left.rate_limited ? -1 : 1;
      }

      const cooldownDelta = right.cooldown_seconds - left.cooldown_seconds;
      if (cooldownDelta !== 0) {
        return cooldownDelta;
      }

      return left.name.localeCompare(right.name);
    }),
  );
  const sourceStatusCounts = computed(() => {
    const sources = status.value?.sources ?? [];
    return {
      total: sources.length,
      rateLimited: sources.filter((source) => source.rate_limited).length,
      official: sources.filter((source) => source.official_limit).length,
      protective: sources.filter((source) => !source.official_limit).length,
    };
  });
  const jobStatusRows = computed(() =>
    enabledCoins.value
      .map((coin) => ({
        coin,
        job: getCoinJobSnapshot(coin),
      }))
      .sort((left, right) => {
        const priority: Record<string, number> = {
          error: 0,
          retry_scheduled: 1,
          backfilling: 2,
          queued: 3,
          ready: 4,
          disabled: 5,
        };

        const leftPriority = priority[left.job.state] ?? 99;
        const rightPriority = priority[right.job.state] ?? 99;
        if (leftPriority !== rightPriority) {
          return leftPriority - rightPriority;
        }

        return left.coin.sort_order - right.coin.sort_order;
      }),
  );
  const jobStatusCounts = computed(() => {
    const counts: Record<string, number> = {
      ready: 0,
      backfilling: 0,
      queued: 0,
      retry_scheduled: 0,
      error: 0,
      disabled: 0,
    };

    for (const coin of coins.value) {
      const state = getCoinJobSnapshot(coin).state;
      counts[state] = (counts[state] ?? 0) + 1;
    }

    return counts;
  });

  function getErrorMessage(err: unknown, fallback: string): string {
    if (axios.isAxiosError(err)) {
      const detail = err.response?.data?.detail;
      if (typeof detail === "string" && detail.trim().length > 0) {
        return detail;
      }
      if (typeof err.message === "string" && err.message.trim().length > 0) {
        return err.message;
      }
    }

    return err instanceof Error ? err.message : fallback;
  }

  async function fetchCoins() {
    try {
      coins.value = await irisApi.listCoins();
    } catch (err) {
      dashboardError.value = getErrorMessage(err, "Unable to load coins.");
    }
  }

  async function refreshDashboard() {
    isBootstrapping.value = true;
    dashboardError.value = "";
    try {
      const snapshot: FrontendDashboardSnapshot = await irisApi.getFrontendDashboardSnapshot();

      coins.value = snapshot.coins;
      metrics.value = snapshot.metrics;
      signals.value = snapshot.signals;
      topSignals.value = snapshot.top_signals;
      marketDecisions.value = snapshot.market_decisions;
      patterns.value = snapshot.patterns;
      strategies.value = snapshot.strategies;
      strategyPerformance.value = snapshot.strategy_performance;
      topBacktests.value = snapshot.top_backtests;
      patternFeatures.value = snapshot.pattern_features;
      discoveredPatterns.value = snapshot.discovered_patterns;
      sectors.value = snapshot.sectors;
      sectorMetrics.value = snapshot.sector_payload.items;
      sectorNarratives.value = snapshot.sector_payload.narratives;
      marketCycles.value = snapshot.market_cycles;
      marketRadar.value = snapshot.market_radar;
      marketFlow.value = snapshot.market_flow;
      predictions.value = snapshot.predictions;
      portfolioState.value = snapshot.portfolio_state;
      portfolioPositions.value = snapshot.portfolio_positions;
      portfolioActions.value = snapshot.portfolio_actions;
      status.value = snapshot.status;
      liveSignalCounts.value = Object.fromEntries(
        snapshot.signals.reduce<Map<string, number>>((map, item) => {
          const symbol = item.symbol.toUpperCase();
          map.set(symbol, (map.get(symbol) ?? 0) + 1);
          return map;
        }, new Map()),
      );
      hasDashboardSnapshot.value = true;
      lastDashboardRefreshAt.value = new Date().toISOString();
    } catch (err) {
      dashboardError.value = getErrorMessage(err, "Unable to load dashboard.");
    } finally {
      isBootstrapping.value = false;
    }
  }

  async function bootstrapDashboard() {
    if (hasDashboardSnapshot.value && status.value) {
      ensureDashboardStreamConnected();
      return;
    }

    await refreshDashboard();
    if (hasDashboardSnapshot.value) {
      ensureDashboardStreamConnected();
    }
  }

  function upsertCoin(nextCoin: Coin) {
    const symbol = nextCoin.symbol.toUpperCase();
    const remaining = coins.value.filter((item) => item.symbol.toUpperCase() !== symbol);
    coins.value = [...remaining, nextCoin].sort(
      (left, right) => left.sort_order - right.sort_order || left.symbol.localeCompare(right.symbol),
    );
  }

  function upsertMetric(nextMetric: CoinMetrics | null) {
    if (!nextMetric) {
      return;
    }
    const symbol = nextMetric.symbol.toUpperCase();
    const remaining = metrics.value.filter((item) => item.symbol.toUpperCase() !== symbol);
    metrics.value = [...remaining, nextMetric].sort((left, right) => left.symbol.localeCompare(right.symbol));
  }

  function replaceSignalsForSymbol(symbol: string, nextSignals: Signal[], nextCount: number) {
    const normalizedSymbol = symbol.toUpperCase();
    signals.value = [
      ...nextSignals,
      ...signals.value.filter((item) => item.symbol.toUpperCase() !== normalizedSymbol),
    ]
      .sort(
        (left, right) =>
          new Date(right.candle_timestamp).getTime() - new Date(left.candle_timestamp).getTime() ||
          new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
      )
      .slice(0, 120);
    liveSignalCounts.value = {
      ...liveSignalCounts.value,
      [normalizedSymbol]: nextCount,
    };
    const rankedSignals = [...nextSignals]
      .sort(
        (left, right) =>
          right.priority_score - left.priority_score ||
          new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
      )
      .slice(0, 3);
    topSignals.value = [
      ...rankedSignals,
      ...topSignals.value.filter((item) => item.symbol.toUpperCase() !== normalizedSymbol),
    ]
      .sort(
        (left, right) =>
          right.priority_score - left.priority_score ||
          new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
      )
      .slice(0, 12);
  }

  function replaceMarketDecisionsForSymbol(symbol: string, nextItems: MarketDecision[]) {
    const normalizedSymbol = symbol.toUpperCase();
    marketDecisions.value = [
      ...nextItems,
      ...marketDecisions.value.filter((item) => item.symbol.toUpperCase() !== normalizedSymbol),
    ]
      .sort(
        (left, right) =>
          right.confidence - left.confidence ||
          right.signal_count - left.signal_count ||
          new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
      )
      .slice(0, 12);
  }

  function applyAssetStreamEvent(payload: DashboardAssetStreamEvent) {
    upsertCoin(payload.coin);
    upsertMetric(payload.metrics);
    replaceSignalsForSymbol(payload.symbol, payload.signals, payload.signal_count);
    replaceMarketDecisionsForSymbol(payload.symbol, payload.market_decisions);
    if (payload.coin_market_decision) {
      coinMarketDecisions.value = {
        ...coinMarketDecisions.value,
        [payload.symbol.toUpperCase()]: payload.coin_market_decision,
      };
    }
    lastDashboardRefreshAt.value = payload.timestamp;
    lastLiveEventAt.value = payload.timestamp;
  }

  function applyPortfolioStreamEvent(payload: DashboardPortfolioStreamEvent) {
    portfolioState.value = payload.state;
    portfolioPositions.value = payload.positions;
    portfolioActions.value = payload.actions;
    lastDashboardRefreshAt.value = payload.timestamp;
    lastLiveEventAt.value = payload.timestamp;
  }

  function ensureDashboardStreamConnected() {
    if (typeof window === "undefined" || dashboardEventSource) {
      return;
    }

    liveStreamStatus.value = "connecting";
    dashboardEventSource = new EventSource(buildApiUrl("/frontend/stream/dashboard"));
    dashboardEventSource.onopen = () => {
      liveStreamStatus.value = "connected";
    };
    dashboardEventSource.onerror = () => {
      liveStreamStatus.value = "error";
    };
    dashboardEventSource.addEventListener("asset_snapshot_updated", (event) => {
      const message = event as MessageEvent<string>;
      const payload = JSON.parse(message.data) as DashboardAssetStreamEvent;
      applyAssetStreamEvent(payload);
      liveStreamStatus.value = "connected";
    });
    dashboardEventSource.addEventListener("portfolio_snapshot_updated", (event) => {
      const message = event as MessageEvent<string>;
      const payload = JSON.parse(message.data) as DashboardPortfolioStreamEvent;
      applyPortfolioStreamEvent(payload);
      liveStreamStatus.value = "connected";
    });
  }

  function disconnectDashboardStream() {
    dashboardEventSource?.close();
    dashboardEventSource = null;
    liveStreamStatus.value = "idle";
  }

  async function loadAssetContext(symbol: string) {
    const normalizedSymbol = symbol.toUpperCase();
    const [patternRows, regime, cycleRows, backtests, marketDecision] = await Promise.all([
      irisApi.listCoinPatterns(symbol, 120),
      irisApi.getCoinRegime(symbol),
      irisApi.listMarketCycles(symbol),
      irisApi.getCoinBacktests(symbol, 16),
      irisApi.getCoinMarketDecision(symbol),
    ]);

    activeSymbol.value = normalizedSymbol;
    coinPatternHistory.value = {
      ...coinPatternHistory.value,
      [normalizedSymbol]: patternRows,
    };
    coinRegimes.value = {
      ...coinRegimes.value,
      [normalizedSymbol]: regime,
    };
    coinMarketDecisions.value = {
      ...coinMarketDecisions.value,
      [normalizedSymbol]: marketDecision,
    };
    coinBacktests.value = {
      ...coinBacktests.value,
      [normalizedSymbol]: backtests,
    };
    marketCycles.value = [
      ...marketCycles.value.filter((item) => item.symbol.toUpperCase() !== normalizedSymbol),
      ...cycleRows,
    ];
  }

  async function fetchAssetContext(symbol: string) {
    historyError.value = "";
    try {
      await loadAssetContext(symbol);
      return true;
    } catch (err) {
      historyError.value = getErrorMessage(err, "Unable to load asset context.");
      return false;
    }
  }

  async function fetchHistory(symbol: string, interval = activeInterval.value) {
    isHistoryLoading.value = true;
    historyError.value = "";
    activeSymbol.value = symbol.toUpperCase();
    activeInterval.value = interval;
    try {
      const [historyRows] = await Promise.all([irisApi.getCoinHistory(symbol, interval), loadAssetContext(symbol)]);
      history.value = historyRows;
    } catch (err) {
      history.value = [];
      historyError.value = getErrorMessage(err, "Unable to load price history.");
    } finally {
      isHistoryLoading.value = false;
    }
  }

  async function createCoin(payload: CoinCreatePayload) {
    isCreatingCoin.value = true;
    createCoinError.value = "";
    createCoinSuccess.value = "";

    try {
      const created = await irisApi.createCoin(payload);
      createCoinSuccess.value = `${created.symbol} queued for backfill.`;
      await refreshDashboard();
      return created;
    } catch (err) {
      createCoinError.value = getErrorMessage(err, "Unable to create coin.");
      return null;
    } finally {
      isCreatingCoin.value = false;
    }
  }

  function isJobRunning(symbol: string): boolean {
    return Boolean(runningJobSymbols.value[symbol.toUpperCase()]);
  }

  async function runCoinJob(
    symbol: string,
    mode: "auto" | "backfill" | "latest" = "auto",
    force = true,
  ) {
    const normalizedSymbol = symbol.toUpperCase();
    runningJobSymbols.value = {
      ...runningJobSymbols.value,
      [normalizedSymbol]: true,
    };
    jobRunError.value = "";
    jobRunSuccess.value = "";

    try {
      const queued = await irisApi.runCoinJob(normalizedSymbol, mode, force);
      jobRunSuccess.value = `${queued.symbol} ${queued.mode === "auto" ? "sync" : queued.mode} queued.`;
      await refreshDashboard();
      return queued;
    } catch (err) {
      jobRunError.value = getErrorMessage(err, "Unable to queue coin job.");
      return null;
    } finally {
      runningJobSymbols.value = {
        ...runningJobSymbols.value,
        [normalizedSymbol]: false,
      };
    }
  }

  return {
    activeSymbol,
    activeCoin,
    activeBacktests,
    activeCycles,
    activeInterval,
    activeMarketDecision,
    activeMetrics,
    activePatternSignals,
    activeRegime,
    activeSignals,
    bootstrapDashboard,
    bullishShare,
    coins,
    createCoin,
    createCoinError,
    createCoinSuccess,
    dashboardError,
    dashboardRows,
    disconnectDashboardStream,
    disabledPatternsCount,
    enabledCoins,
    enabledCoinsCount,
    activePatternsCount,
    fetchCoins,
    fetchAssetContext,
    fetchHistory,
    hasDashboardSnapshot,
    hasHistory,
    history,
    historyError,
    isJobRunning,
    isBootstrapping,
    isCreatingCoin,
    isHistoryLoading,
    jobRunError,
    jobRunSuccess,
    jobStatusCounts,
    jobStatusRows,
    lastDashboardRefreshAt,
    lastLiveEventAt,
    liveStreamStatus,
    marketCycles,
    marketFlow,
    marketFlowLeaders,
    marketFlowRelations,
    marketFlowRotations,
    marketFlowSectors,
    marketDecisions,
    marketRadar,
    latestPortfolioActions,
    metrics,
    metricsBySymbol,
    openPortfolioPositions,
    discoveredPatterns,
    portfolioActions,
    portfolioExposure,
    portfolioPositions,
    portfolioPnl,
    portfolioRiskBudget,
    portfolioState,
    portfolioWatchRadar,
    strategies,
    strategyPerformance,
    enabledPatternFeatures,
    patternFeatures,
    patterns,
    patternHealthRows,
    patternRegimeEfficiency,
    predictionJournal,
    predictions,
    recentSignals,
    refreshDashboard,
    runCoinJob,
    sectorMetrics,
    sectorNarratives,
    sectors,
    signalCountsBySymbol,
    signals,
    signalsBySymbol,
    sourceStatusCounts,
    sourceStatusRows,
    status,
    statusTone,
    activeCrossMarketRelations,
    activePredictionJournal,
    hotRadarCoins,
    emergingRadarCoins,
    regimeChangeRadar,
    volatilitySpikeRadar,
    topSectorMetrics,
    topBacktests,
    topMarketDecisionRadar,
    topPortfolioPositions,
    topStrategies,
    topSignals,
  };
});
