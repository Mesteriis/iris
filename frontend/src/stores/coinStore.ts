import axios from "axios";
import { computed, ref } from "vue";
import { defineStore } from "pinia";

import {
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
  const runningJobSymbols = ref<Record<string, boolean>>({});
  const lastDashboardRefreshAt = ref<string | null>(null);

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
        const signalCount = signalsBySymbol.value.get(coin.symbol.toUpperCase())?.length ?? 0;
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
      const [
        coinRows,
        metricRows,
        signalRows,
        topSignalRows,
        topMarketDecisionRows,
        patternRows,
        strategyRows,
        strategyPerformanceRows,
        backtestRows,
        patternFeatureRows,
        discoveredPatternRows,
        sectorRows,
        sectorPayload,
        cycleRows,
        radarPayload,
        flowPayload,
        predictionRows,
        portfolioStatePayload,
        portfolioPositionRows,
        portfolioActionRows,
        systemState,
      ] = await Promise.all([
        irisApi.listCoins(),
        irisApi.listCoinMetrics(),
        irisApi.listSignals(40),
        irisApi.listTopSignals(12),
        irisApi.listTopMarketDecisions(12),
        irisApi.listPatterns(),
        irisApi.listStrategies(40, false),
        irisApi.listStrategyPerformance(12),
        irisApi.listTopBacktests(10),
        irisApi.listPatternFeatures(),
        irisApi.listDiscoveredPatterns(24),
        irisApi.listSectors(),
        irisApi.listSectorMetrics(),
        irisApi.listMarketCycles(),
        irisApi.getMarketRadar(8),
        irisApi.getMarketFlow(8, 60),
        irisApi.listPredictions(24),
        irisApi.getPortfolioState(),
        irisApi.listPortfolioPositions(40),
        irisApi.listPortfolioActions(40),
        irisApi.getStatus(),
      ]);

      coins.value = coinRows;
      metrics.value = metricRows;
      signals.value = signalRows;
      topSignals.value = topSignalRows;
      marketDecisions.value = topMarketDecisionRows;
      patterns.value = patternRows;
      strategies.value = strategyRows;
      strategyPerformance.value = strategyPerformanceRows;
      topBacktests.value = backtestRows;
      patternFeatures.value = patternFeatureRows;
      discoveredPatterns.value = discoveredPatternRows;
      sectors.value = sectorRows;
      sectorMetrics.value = sectorPayload.items;
      sectorNarratives.value = sectorPayload.narratives;
      marketCycles.value = cycleRows;
      marketRadar.value = radarPayload;
      marketFlow.value = flowPayload;
      predictions.value = predictionRows;
      portfolioState.value = portfolioStatePayload;
      portfolioPositions.value = portfolioPositionRows;
      portfolioActions.value = portfolioActionRows;
      status.value = systemState;
      lastDashboardRefreshAt.value = new Date().toISOString();
    } catch (err) {
      dashboardError.value = getErrorMessage(err, "Unable to load dashboard.");
    } finally {
      isBootstrapping.value = false;
    }
  }

  async function bootstrapDashboard() {
    if (coins.value.length > 0 && metrics.value.length > 0 && status.value) {
      return;
    }

    await refreshDashboard();
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
    disabledPatternsCount,
    enabledCoins,
    enabledCoinsCount,
    activePatternsCount,
    fetchCoins,
    fetchAssetContext,
    fetchHistory,
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
