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
  sector: string | null;
  source: string;
  enabled: boolean;
  auto_watch_enabled: boolean;
  auto_watch_source: string | null;
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
  sector?: string;
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
  activity_score: number | null;
  activity_bucket: "HOT" | "WARM" | "COLD" | "DEAD" | null;
  analysis_priority: number | null;
  last_analysis_at: string | null;
  market_regime: "bull_trend" | "bear_trend" | "sideways_range" | "high_volatility" | "low_volatility" | null;
  market_regime_details: Record<string, RegimeSnapshot> | null;
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
  market_regime: string;
  sample_size: number;
  total_signals: number;
  successful_signals: number;
  success_rate: number;
  avg_return: number;
  avg_drawdown: number;
  temperature: number;
  enabled: boolean;
  last_evaluated_at: string | null;
  updated_at: string;
}

export interface MarketDecision {
  id: number;
  coin_id: number;
  symbol: string;
  name: string;
  sector: string | null;
  timeframe: number;
  decision: "BUY" | "SELL" | "HOLD" | "WATCH";
  confidence: number;
  signal_count: number;
  regime: string | null;
  created_at: string;
}

export interface PortfolioPosition {
  id: number;
  coin_id: number;
  symbol: string;
  name: string;
  sector: string | null;
  exchange_account_id: number | null;
  source_exchange: string | null;
  position_type: string;
  timeframe: number;
  entry_price: number;
  position_size: number;
  position_value: number;
  stop_loss: number | null;
  take_profit: number | null;
  status: "open" | "closed" | "partial";
  opened_at: string;
  closed_at: string | null;
  current_price: number | null;
  unrealized_pnl: number;
  latest_decision: "BUY" | "SELL" | "HOLD" | "WATCH" | null;
  latest_decision_confidence: number | null;
  regime: string | null;
  risk_to_stop: number | null;
}

export interface PortfolioAction {
  id: number;
  coin_id: number;
  symbol: string;
  name: string;
  action: "OPEN_POSITION" | "CLOSE_POSITION" | "REDUCE_POSITION" | "INCREASE_POSITION" | "HOLD_POSITION";
  size: number;
  confidence: number;
  decision_id: number;
  market_decision: "BUY" | "SELL" | "HOLD" | "WATCH";
  created_at: string;
}

export interface PortfolioState {
  total_capital: number;
  allocated_capital: number;
  available_capital: number;
  updated_at: string | null;
  open_positions: number;
  max_positions: number;
}

export interface CoinMarketDecisionItem {
  timeframe: number;
  decision: "BUY" | "SELL" | "HOLD" | "WATCH";
  confidence: number;
  signal_count: number;
  regime: string | null;
  created_at: string | null;
}

export interface CoinMarketDecision {
  coin_id: number;
  symbol: string;
  canonical_decision: "BUY" | "SELL" | "HOLD" | "WATCH" | null;
  items: CoinMarketDecisionItem[];
}

export interface StrategyRule {
  pattern_slug: string;
  regime: string;
  sector: string;
  cycle: string;
  min_confidence: number;
}

export interface StrategyPerformance {
  strategy_id: number;
  name: string;
  enabled: boolean;
  sample_size: number;
  win_rate: number;
  avg_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  updated_at: string;
}

export interface Strategy {
  id: number;
  name: string;
  description: string;
  enabled: boolean;
  created_at: string;
  rules: StrategyRule[];
  performance: StrategyPerformance | null;
}

export interface BacktestSummary {
  symbol: string | null;
  signal_type: string;
  timeframe: number;
  sample_size: number;
  coin_count: number;
  win_rate: number;
  roi: number;
  avg_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  avg_confidence: number;
  last_evaluated_at: string | null;
}

export interface CoinBacktests {
  coin_id: number;
  symbol: string;
  items: BacktestSummary[];
}

export interface MarketRadarCoin {
  coin_id: number;
  symbol: string;
  name: string;
  activity_score: number | null;
  activity_bucket: "HOT" | "WARM" | "COLD" | "DEAD" | null;
  analysis_priority: number | null;
  price_change_24h: number | null;
  price_change_7d: number | null;
  volatility: number | null;
  market_regime: string | null;
  updated_at: string | null;
  last_analysis_at: string | null;
}

export interface MarketRegimeChange {
  coin_id: number;
  symbol: string;
  name: string;
  timeframe: number;
  regime: string;
  confidence: number;
  timestamp: string;
}

export interface MarketRadar {
  hot_coins: MarketRadarCoin[];
  emerging_coins: MarketRadarCoin[];
  regime_changes: MarketRegimeChange[];
  volatility_spikes: MarketRadarCoin[];
}

export interface MarketFlowLeader {
  leader_coin_id: number;
  symbol: string;
  name: string;
  sector: string | null;
  regime: string | null;
  confidence: number;
  price_change_24h: number | null;
  volume_change_24h: number | null;
  timestamp: string;
}

export interface MarketFlowRelation {
  leader_coin_id: number;
  leader_symbol: string;
  follower_coin_id: number;
  follower_symbol: string;
  correlation: number;
  lag_hours: number;
  confidence: number;
  updated_at: string;
}

export interface MarketFlowSector {
  sector_id: number;
  sector: string;
  timeframe: number;
  avg_price_change_24h: number;
  avg_volume_change_24h: number;
  volatility: number;
  trend: string | null;
  relative_strength: number;
  capital_flow: number;
  updated_at: string;
}

export interface MarketFlowRotation {
  source_sector: string;
  target_sector: string;
  timeframe: number;
  timestamp: string;
}

export interface MarketFlow {
  leaders: MarketFlowLeader[];
  relations: MarketFlowRelation[];
  sectors: MarketFlowSector[];
  rotations: MarketFlowRotation[];
}

export interface Prediction {
  id: number;
  prediction_type: string;
  leader_coin_id: number;
  leader_symbol: string;
  target_coin_id: number;
  target_symbol: string;
  prediction_event: string;
  expected_move: string;
  lag_hours: number;
  confidence: number;
  created_at: string;
  evaluation_time: string;
  status: "pending" | "confirmed" | "failed" | "expired";
  actual_move: number | null;
  success: boolean | null;
  profit: number | null;
  evaluated_at: string | null;
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

export interface PatternFeature {
  feature_slug: string;
  enabled: boolean;
  created_at: string;
}

export interface DiscoveredPattern {
  structure_hash: string;
  timeframe: number;
  sample_size: number;
  avg_return: number;
  avg_drawdown: number;
  confidence: number;
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
  avg_price_change_24h: number;
  avg_volume_change_24h: number;
  volatility: number;
  trend: string | null;
  updated_at: string;
}

export interface SectorNarrative {
  timeframe: number;
  top_sector: string | null;
  rotation_state: string | null;
  btc_dominance: number | null;
  capital_wave: string | null;
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

export type ControlPlaneAccessMode = "observe" | "control";
export type ControlPlaneRouteStatus = "active" | "muted" | "paused" | "throttled" | "shadow" | "disabled";
export type ControlPlaneRouteScope = "global" | "domain" | "symbol" | "exchange" | "timeframe" | "environment";

export interface ControlPlaneHeaders {
  actor: string;
  accessMode: ControlPlaneAccessMode;
  reason?: string;
  token?: string;
}

export interface ControlPlaneRouteFilters {
  symbol: string[];
  timeframe: number[];
  exchange: string[];
  confidence: number | null;
  metadata: Record<string, unknown>;
}

export interface ControlPlaneRouteThrottle {
  limit: number | null;
  window_seconds: number;
}

export interface ControlPlaneRouteShadow {
  enabled: boolean;
  sample_rate: number;
  observe_only: boolean;
}

export interface ControlPlaneEventDefinition {
  id: number;
  event_type: string;
  display_name: string;
  domain: string;
  description: string;
  is_control_event: boolean;
  payload_schema_json: Record<string, unknown>;
  routing_hints_json: Record<string, unknown>;
}

export interface ControlPlaneConsumer {
  id: number;
  consumer_key: string;
  display_name: string;
  domain: string;
  description: string;
  implementation_key: string;
  delivery_mode: string;
  delivery_stream: string;
  supports_shadow: boolean;
  compatible_event_types_json: string[];
  supported_filter_fields_json: string[];
  supported_scopes_json: string[];
  settings_json: Record<string, unknown>;
}

export interface ControlPlaneCompatibleConsumer {
  consumer_key: string;
  display_name: string;
  domain: string;
  supports_shadow: boolean;
  supported_filter_fields: string[];
  supported_scopes: string[];
}

export interface ControlPlaneRoute {
  id: number;
  route_key: string;
  event_type: string;
  consumer_key: string;
  status: ControlPlaneRouteStatus;
  scope_type: ControlPlaneRouteScope;
  scope_value: string | null;
  environment: string;
  filters: ControlPlaneRouteFilters;
  throttle: ControlPlaneRouteThrottle;
  shadow: ControlPlaneRouteShadow;
  notes: string | null;
  priority: number;
  system_managed: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ControlPlaneNode {
  id: string;
  node_type: "event" | "consumer";
  key: string;
  label: string;
  domain: string;
  metadata: Record<string, unknown>;
}

export interface ControlPlaneEdge {
  id: string;
  route_key: string;
  source: string;
  target: string;
  status: ControlPlaneRouteStatus;
  scope_type: ControlPlaneRouteScope;
  scope_value: string | null;
  environment: string;
  filters: ControlPlaneRouteFilters;
  throttle: ControlPlaneRouteThrottle;
  shadow: ControlPlaneRouteShadow;
  notes: string | null;
  priority: number;
  system_managed: boolean;
  compatible: boolean;
}

export interface ControlPlaneGraph {
  version_number: number;
  created_at: string | null;
  nodes: ControlPlaneNode[];
  edges: ControlPlaneEdge[];
  palette: {
    events: string[];
    consumers: string[];
  };
  compatibility: Record<string, string[]>;
}

export interface ControlPlaneDraft {
  id: number;
  name: string;
  description: string | null;
  status: "draft" | "applied" | "discarded";
  access_mode: ControlPlaneAccessMode;
  base_version_id: number | null;
  created_by: string;
  applied_version_id: number | null;
  created_at: string;
  updated_at: string;
  applied_at: string | null;
  discarded_at: string | null;
}

export interface ControlPlaneDraftCreatePayload {
  name: string;
  description?: string;
  access_mode?: ControlPlaneAccessMode;
}

export interface ControlPlaneDraftChangePayload {
  change_type: "route_created" | "route_updated" | "route_deleted" | "route_status_changed";
  target_route_key?: string;
  payload: Record<string, unknown>;
}

export interface ControlPlaneDraftChange {
  id: number;
  draft_id: number;
  change_type: "route_created" | "route_updated" | "route_deleted" | "route_status_changed";
  target_route_key: string | null;
  payload_json: Record<string, unknown>;
  created_by: string;
  created_at: string;
}

export interface ControlPlaneDraftDiffItem {
  change_type: "route_created" | "route_updated" | "route_deleted" | "route_status_changed";
  route_key: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
}

export interface ControlPlaneAuditEntry {
  id: number;
  route_key_snapshot: string;
  action: string;
  actor: string;
  actor_mode: ControlPlaneAccessMode;
  reason: string | null;
  before_json: Record<string, unknown>;
  after_json: Record<string, unknown>;
  context_json: Record<string, unknown>;
  created_at: string;
}

export interface ControlPlaneDraftLifecycle {
  draft: ControlPlaneDraft;
  published_version_number: number | null;
}

export interface ControlPlaneObservabilityRoute {
  route_key: string;
  event_type: string;
  consumer_key: string;
  status: ControlPlaneRouteStatus;
  throughput: number;
  failure_count: number;
  avg_latency_ms: number | null;
  last_delivered_at: string | null;
  last_completed_at: string | null;
  lag_seconds: number | null;
  shadow_count: number;
  muted: boolean;
  last_reason: string | null;
}

export interface ControlPlaneObservabilityConsumer {
  consumer_key: string;
  domain: string;
  processed_total: number;
  failure_count: number;
  avg_latency_ms: number | null;
  last_seen_at: string | null;
  last_failure_at: string | null;
  lag_seconds: number | null;
  dead: boolean;
  supports_shadow: boolean;
  delivery_stream: string;
  last_error: string | null;
}

export interface ControlPlaneObservabilityOverview {
  version_number: number;
  generated_at: string;
  throughput: number;
  failure_count: number;
  shadow_route_count: number;
  muted_route_count: number;
  dead_consumer_count: number;
  routes: ControlPlaneObservabilityRoute[];
  consumers: ControlPlaneObservabilityConsumer[];
}

function buildControlPlaneHeaders(context?: Partial<ControlPlaneHeaders>): Record<string, string> | undefined {
  if (!context?.actor && !context?.token && !context?.reason && !context?.accessMode) {
    return undefined;
  }

  const headers: Record<string, string> = {};
  if (context.actor) {
    headers["X-IRIS-Actor"] = context.actor;
  }
  if (context.accessMode) {
    headers["X-IRIS-Access-Mode"] = context.accessMode;
  }
  if (context.reason) {
    headers["X-IRIS-Reason"] = context.reason;
  }
  if (context.token) {
    headers["X-IRIS-Control-Token"] = context.token;
  }
  return headers;
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "/api/v1",
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
  async listMarketDecisions(limit = 24): Promise<MarketDecision[]> {
    const response = await api.get<MarketDecision[]>("/market-decisions", {
      params: { limit },
    });
    return response.data;
  },
  async listTopMarketDecisions(limit = 12): Promise<MarketDecision[]> {
    const response = await api.get<MarketDecision[]>("/market-decisions/top", {
      params: { limit },
    });
    return response.data;
  },
  async getCoinMarketDecision(symbol: string): Promise<CoinMarketDecision> {
    const response = await api.get<CoinMarketDecision>(`/coins/${symbol}/market-decision`);
    return response.data;
  },
  async listPatterns(): Promise<PatternDescriptor[]> {
    const response = await api.get<PatternDescriptor[]>("/patterns");
    return response.data;
  },
  async listStrategies(limit = 40, enabledOnly = false): Promise<Strategy[]> {
    const response = await api.get<Strategy[]>("/strategies", {
      params: { limit, enabled_only: enabledOnly },
    });
    return response.data;
  },
  async listStrategyPerformance(limit = 20): Promise<StrategyPerformance[]> {
    const response = await api.get<StrategyPerformance[]>("/strategies/performance", {
      params: { limit },
    });
    return response.data;
  },
  async listBacktests(limit = 100, timeframe?: number, signalType?: string): Promise<BacktestSummary[]> {
    const response = await api.get<BacktestSummary[]>("/backtests", {
      params: {
        limit,
        ...(timeframe ? { timeframe } : {}),
        ...(signalType ? { signal_type: signalType } : {}),
      },
    });
    return response.data;
  },
  async listTopBacktests(limit = 12, timeframe?: number): Promise<BacktestSummary[]> {
    const response = await api.get<BacktestSummary[]>("/backtests/top", {
      params: {
        limit,
        ...(timeframe ? { timeframe } : {}),
      },
    });
    return response.data;
  },
  async getCoinBacktests(symbol: string, limit = 20): Promise<CoinBacktests> {
    const response = await api.get<CoinBacktests>(`/coins/${symbol}/backtests`, {
      params: { limit },
    });
    return response.data;
  },
  async listPatternFeatures(): Promise<PatternFeature[]> {
    const response = await api.get<PatternFeature[]>("/patterns/features");
    return response.data;
  },
  async listDiscoveredPatterns(limit = 40): Promise<DiscoveredPattern[]> {
    const response = await api.get<DiscoveredPattern[]>("/patterns/discovered", {
      params: { limit },
    });
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
  async getMarketRadar(limit = 8): Promise<MarketRadar> {
    const response = await api.get<MarketRadar>("/market/radar", {
      params: { limit },
    });
    return response.data;
  },
  async getMarketFlow(limit = 8, timeframe = 60): Promise<MarketFlow> {
    const response = await api.get<MarketFlow>("/market/flow", {
      params: { limit, timeframe },
    });
    return response.data;
  },
  async listPredictions(limit = 50, status?: Prediction["status"]): Promise<Prediction[]> {
    const response = await api.get<Prediction[]>("/predictions", {
      params: {
        limit,
        ...(status ? { status } : {}),
      },
    });
    return response.data;
  },
  async listPortfolioPositions(limit = 100): Promise<PortfolioPosition[]> {
    const response = await api.get<PortfolioPosition[]>("/portfolio/positions", {
      params: { limit },
    });
    return response.data;
  },
  async listPortfolioActions(limit = 100): Promise<PortfolioAction[]> {
    const response = await api.get<PortfolioAction[]>("/portfolio/actions", {
      params: { limit },
    });
    return response.data;
  },
  async getPortfolioState(): Promise<PortfolioState> {
    const response = await api.get<PortfolioState>("/portfolio/state");
    return response.data;
  },
  async getStatus(): Promise<SystemStatus> {
    const response = await api.get<SystemStatus>("/system/status");
    return response.data;
  },
  async getCoinHistory(symbol: string, interval: CandleInterval): Promise<PriceHistoryPoint[]> {
    const response = await api.get<PriceHistoryPoint[]>(`/coins/${symbol}/history`, {
      params: { interval },
    });
    return response.data;
  },
  async listControlPlaneEvents(): Promise<ControlPlaneEventDefinition[]> {
    const response = await api.get<ControlPlaneEventDefinition[]>("/control-plane/registry/events");
    return response.data;
  },
  async listControlPlaneConsumers(): Promise<ControlPlaneConsumer[]> {
    const response = await api.get<ControlPlaneConsumer[]>("/control-plane/registry/consumers");
    return response.data;
  },
  async listControlPlaneCompatibleConsumers(eventType: string): Promise<ControlPlaneCompatibleConsumer[]> {
    const response = await api.get<ControlPlaneCompatibleConsumer[]>(
      `/control-plane/registry/events/${eventType}/compatible-consumers`,
    );
    return response.data;
  },
  async listControlPlaneRoutes(): Promise<ControlPlaneRoute[]> {
    const response = await api.get<ControlPlaneRoute[]>("/control-plane/routes");
    return response.data;
  },
  async getControlPlaneGraph(): Promise<ControlPlaneGraph> {
    const response = await api.get<ControlPlaneGraph>("/control-plane/topology/graph");
    return response.data;
  },
  async listControlPlaneDrafts(): Promise<ControlPlaneDraft[]> {
    const response = await api.get<ControlPlaneDraft[]>("/control-plane/drafts");
    return response.data;
  },
  async createControlPlaneDraft(
    payload: ControlPlaneDraftCreatePayload,
    context: ControlPlaneHeaders,
  ): Promise<ControlPlaneDraft> {
    const response = await api.post<ControlPlaneDraft>("/control-plane/drafts", payload, {
      headers: buildControlPlaneHeaders(context),
    });
    return response.data;
  },
  async createControlPlaneDraftChange(
    draftId: number,
    payload: ControlPlaneDraftChangePayload,
    context: ControlPlaneHeaders,
  ): Promise<ControlPlaneDraftChange> {
    const response = await api.post<ControlPlaneDraftChange>(`/control-plane/drafts/${draftId}/changes`, payload, {
      headers: buildControlPlaneHeaders(context),
    });
    return response.data;
  },
  async getControlPlaneDraftDiff(draftId: number): Promise<ControlPlaneDraftDiffItem[]> {
    const response = await api.get<ControlPlaneDraftDiffItem[]>(`/control-plane/drafts/${draftId}/diff`);
    return response.data;
  },
  async applyControlPlaneDraft(draftId: number, context: ControlPlaneHeaders): Promise<ControlPlaneDraftLifecycle> {
    const response = await api.post<ControlPlaneDraftLifecycle>(`/control-plane/drafts/${draftId}/apply`, null, {
      headers: buildControlPlaneHeaders(context),
    });
    return response.data;
  },
  async discardControlPlaneDraft(
    draftId: number,
    context: ControlPlaneHeaders,
  ): Promise<ControlPlaneDraftLifecycle> {
    const response = await api.post<ControlPlaneDraftLifecycle>(`/control-plane/drafts/${draftId}/discard`, null, {
      headers: buildControlPlaneHeaders(context),
    });
    return response.data;
  },
  async listControlPlaneAudit(limit = 50): Promise<ControlPlaneAuditEntry[]> {
    const response = await api.get<ControlPlaneAuditEntry[]>("/control-plane/audit", {
      params: { limit },
    });
    return response.data;
  },
  async getControlPlaneObservability(): Promise<ControlPlaneObservabilityOverview> {
    const response = await api.get<ControlPlaneObservabilityOverview>("/control-plane/observability");
    return response.data;
  },
};
