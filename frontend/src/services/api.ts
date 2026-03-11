import axios from "axios";

export type CandleInterval = "15m" | "1h" | "4h" | "1d";

export interface CandlePolicy {
  interval: CandleInterval;
  retention_bars: number;
}

export interface Coin {
  id: number;
  symbol: string;
  name: string;
  asset_type: string;
  theme: string;
  source: string;
  enabled: boolean;
  sort_order: number;
  candles: CandlePolicy[];
  created_at: string;
  history_backfill_completed_at: string | null;
  last_history_sync_at: string | null;
  next_history_sync_at: string | null;
  last_history_sync_error: string | null;
}

export interface CoinCreatePayload {
  symbol: string;
  name: string;
  asset_type?: string;
  theme?: string;
  source?: string;
  enabled?: boolean;
  sort_order?: number;
  candles?: CandlePolicy[];
}

export interface PriceHistoryPoint {
  interval: CandleInterval;
  coin_id: number;
  timestamp: string;
  price: number;
  volume: number | null;
}

export interface CoinMetrics {
  coin_id: number;
  symbol: string;
  name: string;
  price_current: number | null;
  price_change_1h: number | null;
  price_change_24h: number | null;
  price_change_7d: number | null;
  ema_20: number | null;
  ema_50: number | null;
  sma_50: number | null;
  sma_200: number | null;
  rsi_14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  atr_14: number | null;
  bb_upper: number | null;
  bb_middle: number | null;
  bb_lower: number | null;
  bb_width: number | null;
  adx_14: number | null;
  volume_24h: number | null;
  volume_change_24h: number | null;
  volatility: number | null;
  market_cap: number | null;
  trend: "bullish" | "bearish" | "sideways" | null;
  trend_score: number | null;
  market_regime: "bull_market" | "bear_market" | "accumulation" | "distribution" | null;
  indicator_version: number | null;
  updated_at: string | null;
}

export interface Signal {
  id: number;
  coin_id: number;
  symbol: string;
  name: string;
  sector: string | null;
  timeframe: number;
  signal_type: string;
  confidence: number;
  priority_score: number;
  context_score: number;
  regime_alignment: number;
  candle_timestamp: string;
  created_at: string;
  market_regime: string | null;
  cycle_phase: string | null;
  cycle_confidence: number | null;
  cluster_membership: string[];
}

export interface PatternStatistic {
  timeframe: number;
  sample_size: number;
  success_rate: number;
  avg_return: number;
  avg_drawdown: number;
  temperature: number;
  updated_at: string;
}

export interface PatternDescriptor {
  slug: string;
  category: string;
  enabled: boolean;
  cpu_cost: number;
  lifecycle_state: string;
  created_at: string;
  statistics: PatternStatistic[];
}

export interface RegimeSnapshot {
  timeframe: number;
  regime: string;
  confidence: number;
}

export interface CoinRegime {
  coin_id: number;
  symbol: string;
  canonical_regime: string | null;
  items: RegimeSnapshot[];
}

export interface Sector {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  coin_count: number;
}

export interface SectorMetric {
  sector_id: number;
  name: string;
  description: string | null;
  timeframe: number;
  sector_strength: number;
  relative_strength: number;
  capital_flow: number;
  volatility: number;
  updated_at: string;
}

export interface SectorNarrative {
  timeframe: number;
  top_sector: string | null;
  rotation_state: string | null;
  btc_dominance: number | null;
}

export interface SectorMetricsResponse {
  items: SectorMetric[];
  narratives: SectorNarrative[];
}

export interface MarketCycle {
  coin_id: number;
  symbol: string;
  name: string;
  timeframe: number;
  cycle_phase: string;
  confidence: number;
  detected_at: string;
}

export interface SystemStatus {
  service: string;
  status: string;
  taskiq_mode: string;
  taskiq_running: boolean;
  sources: SourceStatus[];
}

export interface SourceStatus {
  name: string;
  asset_types: string[];
  supported_intervals: CandleInterval[];
  official_limit: boolean;
  rate_limited: boolean;
  cooldown_seconds: number;
  next_available_at: string | null;
  requests_per_window: number | null;
  window_seconds: number | null;
  min_interval_seconds: number | null;
  request_cost: number | null;
  fallback_retry_after_seconds: number | null;
}

export interface CoinJobRunResponse {
  status: string;
  symbol: string;
  mode: "auto" | "backfill" | "latest";
  force: boolean;
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "/api",
  timeout: 10000,
});

export const irisApi = {
  async listCoins(): Promise<Coin[]> {
    const response = await api.get<Coin[]>("/coins");
    return response.data;
  },
  async createCoin(payload: CoinCreatePayload): Promise<Coin> {
    const response = await api.post<Coin>("/coins", payload);
    return response.data;
  },
  async runCoinJob(
    symbol: string,
    mode: "auto" | "backfill" | "latest" = "auto",
    force = true,
  ): Promise<CoinJobRunResponse> {
    const response = await api.post<CoinJobRunResponse>(`/coins/${symbol}/jobs/run`, null, {
      params: { mode, force },
    });
    return response.data;
  },
  async listCoinMetrics(): Promise<CoinMetrics[]> {
    const response = await api.get<CoinMetrics[]>("/coins/metrics");
    return response.data;
  },
  async listSignals(limit = 24): Promise<Signal[]> {
    const response = await api.get<Signal[]>("/signals", {
      params: { limit },
    });
    return response.data;
  },
  async listTopSignals(limit = 12): Promise<Signal[]> {
    const response = await api.get<Signal[]>("/signals/top", {
      params: { limit },
    });
    return response.data;
  },
  async listPatterns(): Promise<PatternDescriptor[]> {
    const response = await api.get<PatternDescriptor[]>("/patterns");
    return response.data;
  },
  async listCoinPatterns(symbol: string, limit = 120): Promise<Signal[]> {
    const response = await api.get<Signal[]>(`/coins/${symbol}/patterns`, {
      params: { limit },
    });
    return response.data;
  },
  async getCoinRegime(symbol: string): Promise<CoinRegime> {
    const response = await api.get<CoinRegime>(`/coins/${symbol}/regime`);
    return response.data;
  },
  async listSectors(): Promise<Sector[]> {
    const response = await api.get<Sector[]>("/sectors");
    return response.data;
  },
  async listSectorMetrics(timeframe?: number): Promise<SectorMetricsResponse> {
    const response = await api.get<SectorMetricsResponse>("/sectors/metrics", {
      params: timeframe ? { timeframe } : undefined,
    });
    return response.data;
  },
  async listMarketCycles(symbol?: string, timeframe?: number): Promise<MarketCycle[]> {
    const response = await api.get<MarketCycle[]>("/market/cycle", {
      params: {
        ...(symbol ? { symbol } : {}),
        ...(timeframe ? { timeframe } : {}),
      },
    });
    return response.data;
  },
  async getStatus(): Promise<SystemStatus> {
    const response = await api.get<SystemStatus>("/status");
    return response.data;
  },
  async getCoinHistory(symbol: string, interval: CandleInterval): Promise<PriceHistoryPoint[]> {
    const response = await api.get<PriceHistoryPoint[]>(`/coins/${symbol}/history`, {
      params: { interval },
    });
    return response.data;
  },
};
