<script setup lang="ts">
import { computed, onMounted, reactive } from "vue";

import { useCoinStore } from "../stores/coinStore";
import {
  formatCompactNumber,
  formatCurrency,
  formatCurrencyDelta,
  formatDateTime,
  formatDurationSeconds,
  formatMarketRegime,
  formatPercent,
  formatRateLimitPolicy,
  formatSignalType,
  formatTrend,
  timeframeToLabel,
} from "../utils/format";

const coinStore = useCoinStore();
const leadRows = computed(() => coinStore.dashboardRows.slice(0, 3));
const addCoinForm = reactive({
  symbol: "",
  name: "",
  asset_type: "crypto",
  theme: "core",
  source: "default",
  enabled: true,
  sort_order: 500,
});

onMounted(async () => {
  await coinStore.bootstrapDashboard();
});

async function submitCoinForm() {
  const created = await coinStore.createCoin({
    symbol: addCoinForm.symbol,
    name: addCoinForm.name,
    asset_type: addCoinForm.asset_type,
    theme: addCoinForm.theme,
    source: addCoinForm.source,
    enabled: addCoinForm.enabled,
    sort_order: addCoinForm.sort_order,
  });

  if (!created) {
    return;
  }

  addCoinForm.symbol = "";
  addCoinForm.name = "";
  addCoinForm.asset_type = "crypto";
  addCoinForm.theme = "core";
  addCoinForm.source = "default";
  addCoinForm.enabled = true;
  addCoinForm.sort_order = 500;
}

async function runCoinJob(symbol: string) {
  await coinStore.runCoinJob(symbol, "auto", true);
}
</script>

<template>
  <section class="dashboard-grid">
    <div class="hero-panel">
      <div class="hero-panel__copy">
        <p class="hero-panel__eyebrow">Market pulse</p>
        <h2>Precomputed analytics for position trading, trend selection and regime reads.</h2>
        <p>
          Every card below is backed by `coin_metrics`, `signals` and aggregated candles. The UI
          never scans raw history tables.
        </p>
      </div>

      <div class="hero-panel__stats">
        <article class="mini-stat">
          <span>Tracked assets</span>
          <strong>{{ coinStore.enabledCoinsCount }}</strong>
          <small>enabled in backend watchlist</small>
        </article>
        <article class="mini-stat">
          <span>Bullish share</span>
          <strong>{{ coinStore.bullishShare }}%</strong>
          <small>coins with bullish trend state</small>
        </article>
        <article class="mini-stat">
          <span>Signal flow</span>
          <strong>{{ coinStore.signals.length }}</strong>
          <small>latest non-repainting events</small>
        </article>
        <article class="mini-stat">
          <span>Last refresh</span>
          <strong>{{ formatDateTime(coinStore.lastDashboardRefreshAt) }}</strong>
          <small>dashboard snapshot time</small>
        </article>
      </div>
    </div>

    <section class="surface-card surface-card--hero">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Conviction ladder</p>
          <h3>Leaders by trend score</h3>
        </div>
        <button class="action-chip" type="button" @click="coinStore.refreshDashboard()">Reload board</button>
      </div>

      <div v-if="coinStore.isBootstrapping" class="surface-state">Loading dashboard...</div>
      <div v-else-if="coinStore.dashboardError" class="surface-state surface-state--error">
        {{ coinStore.dashboardError }}
      </div>
      <div v-else class="leader-grid">
        <RouterLink
          v-for="row in leadRows"
          :key="row.symbol"
          :to="`/coins/${row.symbol}`"
          class="leader-card"
        >
          <div class="leader-card__header">
            <div>
              <p class="leader-card__symbol">{{ row.symbol }}</p>
              <p class="leader-card__name">{{ row.name }}</p>
            </div>
            <span class="trend-badge" :class="`trend-badge--${row.trend ?? 'pending'}`">
              {{ formatTrend(row.trend) }}
            </span>
          </div>

          <div class="leader-card__price">{{ formatCurrency(row.price_current ?? null) }}</div>

          <dl class="leader-card__metrics">
            <div>
              <dt>24h delta</dt>
              <dd :class="{ positive: (row.price_change_24h ?? 0) > 0, negative: (row.price_change_24h ?? 0) < 0 }">
                {{ formatCurrencyDelta(row.price_change_24h) }}
              </dd>
            </div>
            <div>
              <dt>Score</dt>
              <dd>{{ row.trend_score ?? "No data" }}</dd>
            </div>
            <div>
              <dt>Regime</dt>
              <dd>{{ formatMarketRegime(row.market_regime) }}</dd>
            </div>
          </dl>
        </RouterLink>
      </div>
    </section>

    <section class="detail-grid__row">
      <article class="surface-card">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Add asset</p>
            <h3>Create tracked coin</h3>
          </div>
          <p>Submitting a new coin triggers backend backfill immediately.</p>
        </div>

        <form class="form-grid" @submit.prevent="submitCoinForm">
          <label class="field">
            <span>Symbol</span>
            <input v-model.trim="addCoinForm.symbol" placeholder="BTCUSD" required type="text" />
          </label>
          <label class="field">
            <span>Name</span>
            <input v-model.trim="addCoinForm.name" placeholder="Bitcoin" required type="text" />
          </label>
          <label class="field">
            <span>Asset type</span>
            <input v-model.trim="addCoinForm.asset_type" placeholder="crypto" type="text" />
          </label>
          <label class="field">
            <span>Theme</span>
            <input v-model.trim="addCoinForm.theme" placeholder="core" type="text" />
          </label>
          <label class="field">
            <span>Source</span>
            <input v-model.trim="addCoinForm.source" placeholder="default" type="text" />
          </label>
          <label class="field">
            <span>Sort order</span>
            <input v-model.number="addCoinForm.sort_order" min="0" step="1" type="number" />
          </label>
          <label class="field field--checkbox">
            <input v-model="addCoinForm.enabled" type="checkbox" />
            <span>Enabled for sync</span>
          </label>
          <div class="form-actions">
            <button class="action-chip" :disabled="coinStore.isCreatingCoin" type="submit">
              {{ coinStore.isCreatingCoin ? "Creating..." : "Add coin" }}
            </button>
            <p v-if="coinStore.createCoinSuccess" class="form-message form-message--ok">
              {{ coinStore.createCoinSuccess }}
            </p>
            <p v-else-if="coinStore.createCoinError" class="form-message form-message--error">
              {{ coinStore.createCoinError }}
            </p>
          </div>
        </form>
      </article>

      <article class="surface-card">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Background jobs</p>
            <h3>Backfill and sync state</h3>
          </div>
          <button class="action-chip" type="button" @click="coinStore.refreshDashboard()">Refresh jobs</button>
        </div>

        <div class="job-summary-grid">
          <div class="indicator-card">
            <span>Ready</span>
            <strong>{{ coinStore.jobStatusCounts.ready }}</strong>
          </div>
          <div class="indicator-card">
            <span>Backfilling</span>
            <strong>{{ coinStore.jobStatusCounts.backfilling }}</strong>
          </div>
          <div class="indicator-card">
            <span>Queued</span>
            <strong>{{ coinStore.jobStatusCounts.queued }}</strong>
          </div>
          <div class="indicator-card">
            <span>Retry</span>
            <strong>{{ coinStore.jobStatusCounts.retry_scheduled }}</strong>
          </div>
          <div class="indicator-card">
            <span>Error</span>
            <strong>{{ coinStore.jobStatusCounts.error }}</strong>
          </div>
        </div>

        <p v-if="coinStore.jobRunSuccess" class="form-message form-message--ok">
          {{ coinStore.jobRunSuccess }}
        </p>
        <p v-else-if="coinStore.jobRunError" class="form-message form-message--error">
          {{ coinStore.jobRunError }}
        </p>

        <ul class="detail-signal-list">
          <li v-for="entry in coinStore.jobStatusRows.slice(0, 8)" :key="entry.coin.symbol">
            <div>
              <strong>{{ entry.coin.symbol }}</strong>
              <p>{{ entry.job.detail }}</p>
            </div>
            <div class="detail-signal-list__meta">
              <span class="job-badge" :class="`job-badge--${entry.job.state}`">{{ entry.job.label }}</span>
              <small>{{ formatDateTime(entry.job.timestamp) }}</small>
              <button
                class="action-chip action-chip--compact"
                :disabled="coinStore.isJobRunning(entry.coin.symbol)"
                type="button"
                @click="runCoinJob(entry.coin.symbol)"
              >
                {{ coinStore.isJobRunning(entry.coin.symbol) ? "Queueing..." : "Run now" }}
              </button>
            </div>
          </li>
        </ul>
      </article>

      <article class="surface-card">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Source cooldowns</p>
            <h3>Provider throttle state</h3>
          </div>
          <button class="action-chip" type="button" @click="coinStore.refreshDashboard()">Refresh sources</button>
        </div>

        <div class="job-summary-grid">
          <div class="indicator-card">
            <span>Sources</span>
            <strong>{{ coinStore.sourceStatusCounts.total }}</strong>
          </div>
          <div class="indicator-card">
            <span>Cooling</span>
            <strong>{{ coinStore.sourceStatusCounts.rateLimited }}</strong>
          </div>
          <div class="indicator-card">
            <span>Official caps</span>
            <strong>{{ coinStore.sourceStatusCounts.official }}</strong>
          </div>
          <div class="indicator-card">
            <span>Protective caps</span>
            <strong>{{ coinStore.sourceStatusCounts.protective }}</strong>
          </div>
        </div>

        <ul class="detail-signal-list">
          <li v-for="source in coinStore.sourceStatusRows" :key="source.name">
            <div>
              <strong>{{ source.name }}</strong>
              <p>
                {{ formatRateLimitPolicy(source.requests_per_window, source.window_seconds, source.request_cost) }}
                · {{ source.asset_types.join(", ") || "no assets" }}
              </p>
            </div>
            <div class="detail-signal-list__meta">
              <span class="source-badge" :class="`source-badge--${source.rate_limited ? 'limited' : 'live'}`">
                {{ source.rate_limited ? "Cooling down" : "Available" }}
              </span>
              <small>
                {{
                  source.rate_limited
                    ? `next ${formatDateTime(source.next_available_at)}`
                    : source.min_interval_seconds
                      ? `${source.min_interval_seconds}s min gap`
                      : "No active cooldown"
                }}
              </small>
              <small class="source-limit-note">
                {{ source.official_limit ? "official policy" : "protective local cap" }}
                <template v-if="source.rate_limited">
                  · {{ formatDurationSeconds(source.cooldown_seconds) }}
                </template>
              </small>
            </div>
          </li>
        </ul>
      </article>
    </section>

    <section class="detail-grid__row">
      <article class="surface-card">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Top signals</p>
            <h3>Priority-ranked flow</h3>
          </div>
          <p>{{ coinStore.topSignals.length }} ranked items</p>
        </div>

        <div v-if="coinStore.topSignals.length === 0" class="surface-state">
          No prioritized signals yet.
        </div>
        <ul v-else class="detail-signal-list">
          <li v-for="signal in coinStore.topSignals" :key="signal.id">
            <div>
              <strong>{{ signal.symbol }} · {{ formatSignalType(signal.signal_type) }}</strong>
              <p>
                {{ timeframeToLabel(signal.timeframe) }} / {{ formatMarketRegime(signal.market_regime) }}
                <template v-if="signal.cycle_phase"> / {{ signal.cycle_phase }}</template>
                <template v-if="signal.cluster_membership.length > 0">
                  / {{ signal.cluster_membership.map(formatSignalType).join(", ") }}
                </template>
              </p>
            </div>
            <div class="detail-signal-list__meta">
              <span>{{ signal.priority_score.toFixed(3) }}</span>
              <small>{{ Math.round(signal.confidence * 100) }}%</small>
            </div>
          </li>
        </ul>
      </article>

      <article class="surface-card">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Sector rotation</p>
            <h3>Capital flow map</h3>
          </div>
          <p>{{ coinStore.sectors.length }} sectors from current taxonomy</p>
        </div>

        <div class="indicator-grid">
          <div
            v-for="item in coinStore.topSectorMetrics"
            :key="`${item.sector_id}-${item.timeframe}`"
            class="indicator-card"
          >
            <span>{{ item.name }} · {{ timeframeToLabel(item.timeframe) }}</span>
            <strong>{{ formatPercent(item.sector_strength * 100, 2) }}</strong>
            <small>
              RS {{ formatPercent(item.relative_strength * 100, 2) }} · Flow {{ item.capital_flow.toFixed(2) }}
            </small>
          </div>
        </div>

        <ul v-if="coinStore.sectorNarratives.length > 0" class="detail-signal-list">
          <li v-for="narrative in coinStore.sectorNarratives" :key="narrative.timeframe">
            <div>
              <strong>{{ timeframeToLabel(narrative.timeframe) }}</strong>
              <p>
                {{ narrative.top_sector || "No leader" }}
                <template v-if="narrative.capital_wave">
                  / wave {{ narrative.capital_wave }}
                </template>
              </p>
            </div>
            <div class="detail-signal-list__meta">
              <span>{{ narrative.rotation_state || "stable" }}</span>
              <small>
                BTC dom
                {{
                  narrative.btc_dominance !== null
                    ? `${(narrative.btc_dominance * 100).toFixed(1)}%`
                    : "No data"
                }}
              </small>
            </div>
          </li>
        </ul>
      </article>
    </section>

    <section class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Self evolving strategies</p>
          <h3>Top discovered combinations</h3>
        </div>
        <p>{{ coinStore.strategies.length }} stored strategies</p>
      </div>

      <div v-if="coinStore.topStrategies.length === 0" class="surface-state">
        Strategy discovery has not produced ranked strategies yet.
      </div>
      <ul v-else class="detail-signal-list">
        <li v-for="strategy in coinStore.topStrategies" :key="strategy.strategy_id">
          <div>
            <strong>{{ strategy.name }}</strong>
            <p>
              win {{ formatPercent(strategy.win_rate * 100, 2) }}
              / ret {{ formatPercent(strategy.avg_return * 100, 2) }}
              / dd {{ formatPercent(strategy.max_drawdown * 100, 2) }}
            </p>
          </div>
          <div class="detail-signal-list__meta">
            <span>{{ strategy.sharpe_ratio.toFixed(2) }}</span>
            <small>sample {{ strategy.sample_size }}</small>
            <small>{{ strategy.enabled ? "enabled" : "disabled" }}</small>
          </div>
        </li>
      </ul>
    </section>

    <section class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Backtest engine</p>
          <h3>Signals with proven edge</h3>
        </div>
        <p>{{ coinStore.topBacktests.length }} ranked signal stacks</p>
      </div>

      <div v-if="coinStore.topBacktests.length === 0" class="surface-state">
        Backtest engine has not produced signal performance rows yet.
      </div>
      <ul v-else class="detail-signal-list">
        <li v-for="item in coinStore.topBacktests" :key="`${item.signal_type}-${item.timeframe}`">
          <div>
            <strong>{{ formatSignalType(item.signal_type) }}</strong>
            <p>
              {{ timeframeToLabel(item.timeframe) }} / win {{ formatPercent(item.win_rate * 100, 2) }}
              / avg {{ formatPercent(item.avg_return * 100, 2) }}
            </p>
          </div>
          <div class="detail-signal-list__meta">
            <span>{{ item.sharpe_ratio.toFixed(2) }}</span>
            <small>ROI {{ formatPercent(item.roi * 100, 2) }}</small>
            <small>sample {{ item.sample_size }}</small>
          </div>
        </li>
      </ul>
    </section>

    <section class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Pattern library</p>
          <h3>Lifecycle and temperature</h3>
        </div>
        <p>{{ coinStore.patterns.length }} registered detectors</p>
      </div>

      <ul class="detail-signal-list">
        <li v-for="pattern in coinStore.patterns.slice(0, 12)" :key="pattern.slug">
          <div>
            <strong>{{ formatSignalType(pattern.slug) }}</strong>
            <p>{{ pattern.category }} / {{ pattern.lifecycle_state }}</p>
          </div>
          <div class="detail-signal-list__meta">
            <span>
              {{
                pattern.statistics.length > 0
                  ? Math.max(...pattern.statistics.map((item) => item.temperature)).toFixed(3)
                  : "0.000"
              }}
            </span>
            <small>CPU {{ pattern.cpu_cost }}</small>
          </div>
        </li>
      </ul>
    </section>

    <section class="detail-grid__row">
      <article class="surface-card">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Feature flags</p>
            <h3>Subsystem switches</h3>
          </div>
          <p>{{ coinStore.enabledPatternFeatures.length }} enabled</p>
        </div>

        <ul class="detail-signal-list">
          <li v-for="feature in coinStore.patternFeatures" :key="feature.feature_slug">
            <div>
              <strong>{{ formatSignalType(feature.feature_slug) }}</strong>
              <p>{{ formatDateTime(feature.created_at) }}</p>
            </div>
            <div class="detail-signal-list__meta">
              <span>{{ feature.enabled ? "enabled" : "disabled" }}</span>
            </div>
          </li>
        </ul>
      </article>

      <article class="surface-card">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Discovery</p>
            <h3>Review candidates</h3>
          </div>
          <p>{{ coinStore.discoveredPatterns.length }} candidates</p>
        </div>

        <ul v-if="coinStore.discoveredPatterns.length > 0" class="detail-signal-list">
          <li v-for="candidate in coinStore.discoveredPatterns.slice(0, 10)" :key="`${candidate.structure_hash}-${candidate.timeframe}`">
            <div>
              <strong>{{ candidate.structure_hash.slice(0, 12) }}</strong>
              <p>{{ timeframeToLabel(candidate.timeframe) }} / sample {{ candidate.sample_size }}</p>
            </div>
            <div class="detail-signal-list__meta">
              <span>{{ candidate.confidence.toFixed(3) }}</span>
              <small>
                ret {{ formatPercent(candidate.avg_return * 100, 2) }} / dd {{ formatPercent(candidate.avg_drawdown * 100, 2) }}
              </small>
            </div>
          </li>
        </ul>
        <div v-else class="surface-state">
          Discovery engine has not produced review candidates yet.
        </div>
      </article>
    </section>

    <section class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Coverage</p>
          <h3>Tracked market universe</h3>
        </div>
        <p>{{ coinStore.dashboardRows.length }} assets with snapshot rows</p>
      </div>

      <div v-if="coinStore.isBootstrapping" class="surface-state">Loading assets...</div>
      <div v-else-if="coinStore.dashboardRows.length === 0" class="surface-state">
        No tracked assets returned by backend.
      </div>
      <div v-else class="table-shell">
        <table class="data-table">
          <thead>
            <tr>
              <th>Asset</th>
              <th>Type</th>
              <th>Price</th>
              <th>24h</th>
              <th>Trend</th>
              <th>Regime</th>
              <th>Jobs</th>
              <th>Signals</th>
              <th>Market cap</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in coinStore.dashboardRows" :key="row.symbol">
              <td>
                <div class="asset-cell">
                  <strong>{{ row.symbol }}</strong>
                  <span>{{ row.name }}</span>
                </div>
              </td>
              <td>
                <div class="pill-stack">
                  <span class="pill">{{ row.asset_type }}</span>
                  <span class="pill pill--subtle">{{ row.theme }}</span>
                </div>
              </td>
              <td>{{ formatCurrency(row.price_current ?? null) }}</td>
              <td :class="{ positive: (row.price_change_24h ?? 0) > 0, negative: (row.price_change_24h ?? 0) < 0 }">
                {{ formatCurrencyDelta(row.price_change_24h) }}
              </td>
              <td>
                <div class="score-cell">
                  <span class="trend-badge" :class="`trend-badge--${row.trend ?? 'pending'}`">
                    {{ formatTrend(row.trend) }}
                  </span>
                  <small>{{ row.trend_score ?? "No data" }}</small>
                </div>
              </td>
              <td>{{ formatMarketRegime(row.market_regime) }}</td>
              <td>
                <div class="score-cell">
                  <span class="job-badge" :class="`job-badge--${row.job.state}`">{{ row.job.label }}</span>
                  <small>{{ formatDateTime(row.job.timestamp) }}</small>
                </div>
              </td>
              <td>{{ row.signalCount }}</td>
              <td>{{ formatCompactNumber(row.market_cap ?? null) }}</td>
              <td class="table-action">
                <button
                  class="action-chip action-chip--compact"
                  :disabled="coinStore.isJobRunning(row.symbol)"
                  type="button"
                  @click="runCoinJob(row.symbol)"
                >
                  {{ coinStore.isJobRunning(row.symbol) ? "Queueing..." : "Run" }}
                </button>
                <RouterLink class="action-chip" :to="`/coins/${row.symbol}`">Open</RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>
