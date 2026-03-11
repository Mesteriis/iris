import axios from "axios";
import { computed, ref } from "vue";
import { defineStore } from "pinia";

import {
  irisApi,
  type BacktestSummary,
  type CandleInterval,
  type Coin,
  type CoinBacktests,
  type CoinRegime,
  type CoinCreatePayload,
  type CoinMetrics,
  type DiscoveredPattern,
  type MarketCycle,
  type PatternDescriptor,
  type PatternFeature,
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
  const coinBacktests = ref<Record<string, CoinBacktests>>({});
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
    enabledCoins.value.find((coin) => coin.symbol === activeSymbol.value) ?? null,
  );
  const activeMetrics = computed(() => metricsBySymbol.value.get(activeSymbol.value) ?? null);
  const activeSignals = computed(
    () => signalsBySymbol.value.get(activeSymbol.value)?.slice(0, 12) ?? [],
  );
  const activePatternSignals = computed(() => coinPatternHistory.value[activeSymbol.value] ?? []);
  const activeBacktests = computed(() => coinBacktests.value[activeSymbol.value]?.items ?? []);
  const activeRegime = computed(() => coinRegimes.value[activeSymbol.value] ?? null);
  const activeCycles = computed(() =>
    marketCycles.value.filter((item) => item.symbol.toUpperCase() === activeSymbol.value),
  );
  const topSectorMetrics = computed(() => sectorMetrics.value.slice(0, 6));
  const enabledPatternFeatures = computed(() => patternFeatures.value.filter((item) => item.enabled));
  const topStrategies = computed(() => strategyPerformance.value.slice(0, 6));
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
        patternRows,
        strategyRows,
        strategyPerformanceRows,
        backtestRows,
        patternFeatureRows,
        discoveredPatternRows,
        sectorRows,
        sectorPayload,
        cycleRows,
        systemState,
      ] = await Promise.all([
        irisApi.listCoins(),
        irisApi.listCoinMetrics(),
        irisApi.listSignals(40),
        irisApi.listTopSignals(12),
        irisApi.listPatterns(),
        irisApi.listStrategies(40, false),
        irisApi.listStrategyPerformance(12),
        irisApi.listTopBacktests(10),
        irisApi.listPatternFeatures(),
        irisApi.listDiscoveredPatterns(24),
        irisApi.listSectors(),
        irisApi.listSectorMetrics(),
        irisApi.listMarketCycles(),
        irisApi.getStatus(),
      ]);

      coins.value = coinRows;
      metrics.value = metricRows;
      signals.value = signalRows;
      topSignals.value = topSignalRows;
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

  async function fetchHistory(symbol: string, interval = activeInterval.value) {
    isHistoryLoading.value = true;
    historyError.value = "";
    activeSymbol.value = symbol.toUpperCase();
    activeInterval.value = interval;
    try {
      const [historyRows, patternRows, regime, cycleRows, backtests] = await Promise.all([
        irisApi.getCoinHistory(symbol, interval),
        irisApi.listCoinPatterns(symbol, 120),
        irisApi.getCoinRegime(symbol),
        irisApi.listMarketCycles(symbol),
        irisApi.getCoinBacktests(symbol, 16),
      ]);
      history.value = historyRows;
      coinPatternHistory.value = {
        ...coinPatternHistory.value,
        [symbol.toUpperCase()]: patternRows,
      };
      coinRegimes.value = {
        ...coinRegimes.value,
        [symbol.toUpperCase()]: regime,
      };
      coinBacktests.value = {
        ...coinBacktests.value,
        [symbol.toUpperCase()]: backtests,
      };
      marketCycles.value = [
        ...marketCycles.value.filter((item) => item.symbol.toUpperCase() !== symbol.toUpperCase()),
        ...cycleRows,
      ];
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
    enabledCoins,
    enabledCoinsCount,
    fetchCoins,
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
    metrics,
    metricsBySymbol,
    discoveredPatterns,
    strategies,
    strategyPerformance,
    enabledPatternFeatures,
    patternFeatures,
    patterns,
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
    topSectorMetrics,
    topBacktests,
    topStrategies,
    topSignals,
  };
});
