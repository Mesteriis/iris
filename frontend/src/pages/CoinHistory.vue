<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useRoute } from "vue-router";

import PriceChart from "../components/PriceChart.vue";
import { useCoinStore } from "../stores/coinStore";
import type { CandleInterval } from "../services/api";
import {
  formatCompactNumber,
  formatCurrency,
  formatCurrencyDelta,
  formatDateTime,
  formatMarketRegime,
  formatPercent,
  formatSignalType,
  formatTrend,
  timeframeToLabel,
} from "../utils/format";

const route = useRoute();
const coinStore = useCoinStore();
const fallbackIntervals: CandleInterval[] = ["15m", "1h", "4h", "1d"];

const symbol = computed(() => String(route.params.symbol || "").toUpperCase());
const coin = computed(
  () => coinStore.enabledCoins.find((item) => item.symbol === symbol.value) ?? null,
);
const metric = computed(() => coinStore.metricsBySymbol.get(symbol.value) ?? null);
const patternSignals = computed(() => coinStore.activePatternSignals);
const regime = computed(() => coinStore.activeRegime);
const cycles = computed(() => coinStore.activeCycles);
const intervalOptions = computed<CandleInterval[]>(() => {
  const configured = (coin.value?.candles ?? [])
    .map((entry) => entry.interval)
    .filter((entry): entry is CandleInterval => fallbackIntervals.includes(entry as CandleInterval));
  return configured.length > 0 ? configured : fallbackIntervals;
});

async function loadPage() {
  await coinStore.bootstrapDashboard();
  if (symbol.value) {
    const nextInterval = intervalOptions.value.includes(coinStore.activeInterval)
      ? coinStore.activeInterval
      : intervalOptions.value[intervalOptions.value.length - 1];
    await coinStore.fetchHistory(symbol.value, nextInterval);
  }
}

async function selectInterval(interval: CandleInterval) {
  await coinStore.fetchHistory(symbol.value, interval);
}

async function runCoinJob() {
  if (!symbol.value) {
    return;
  }
  const queued = await coinStore.runCoinJob(symbol.value, "auto", true);
  if (queued) {
    await coinStore.fetchHistory(symbol.value, coinStore.activeInterval);
  }
}

onMounted(loadPage);
watch(symbol, loadPage);
</script>

<template>
  <section class="detail-grid">
    <div class="surface-card surface-card--hero">
      <div class="section-head">
        <div>
          <RouterLink class="section-head__eyebrow link-back" to="/">Back to board</RouterLink>
          <h2>{{ coinStore.activeCoin?.name || metric?.name || symbol }}</h2>
          <p>
            Long-term structure, precomputed indicators and non-repainting signals for
            {{ symbol }}.
          </p>
        </div>

        <div class="hero-metrics">
          <article class="mini-stat">
            <span>Current price</span>
            <strong>{{ formatCurrency(metric?.price_current ?? null) }}</strong>
            <small :class="{ positive: (metric?.price_change_24h ?? 0) > 0, negative: (metric?.price_change_24h ?? 0) < 0 }">
              {{ formatCurrencyDelta(metric?.price_change_24h) }}
            </small>
          </article>
          <article class="mini-stat">
            <span>Trend state</span>
            <strong>{{ formatTrend(metric?.trend) }}</strong>
            <small>score {{ metric?.trend_score ?? "No data" }}</small>
          </article>
          <article class="mini-stat">
            <span>Regime</span>
            <strong>{{ formatMarketRegime(metric?.market_regime) }}</strong>
            <small>ADX {{ metric?.adx_14?.toFixed(2) ?? "No data" }}</small>
          </article>
          <article class="mini-stat">
            <span>24h volume</span>
            <strong>{{ formatCompactNumber(metric?.volume_24h ?? null) }}</strong>
            <small>{{ formatPercent(metric?.volume_change_24h) }}</small>
          </article>
        </div>
        <button
          class="action-chip"
          :disabled="coinStore.isJobRunning(symbol)"
          type="button"
          @click="runCoinJob"
        >
          {{ coinStore.isJobRunning(symbol) ? "Queueing sync..." : "Run sync now" }}
        </button>
      </div>
    </div>

    <section class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">History</p>
          <h3>Price and flow</h3>
        </div>
        <div class="interval-switcher" role="tablist" aria-label="History intervals">
          <button
            v-for="interval in intervalOptions"
            :key="interval"
            class="interval-switcher__button"
            :class="{ 'is-active': coinStore.activeInterval === interval }"
            type="button"
            @click="selectInterval(interval)"
          >
            {{ interval }}
          </button>
        </div>
      </div>

      <div v-if="coinStore.isHistoryLoading" class="surface-state">Loading candle history...</div>
      <div v-else-if="coinStore.historyError" class="surface-state surface-state--error">
        {{ coinStore.historyError }}
      </div>
      <div v-else-if="!coinStore.hasHistory" class="surface-state">
        No candle history exists for {{ symbol }} yet.
        <button
          class="action-chip"
          :disabled="coinStore.isJobRunning(symbol)"
          type="button"
          @click="runCoinJob"
        >
          {{ coinStore.isJobRunning(symbol) ? "Queueing sync..." : "Run sync now" }}
        </button>
      </div>
      <PriceChart
        v-else
        :interval="coinStore.activeInterval"
        :points="coinStore.history"
        :symbol="symbol"
      />
    </section>

    <section class="detail-grid__row">
      <article class="surface-card">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Indicators</p>
            <h3>Trend structure</h3>
          </div>
          <p>Updated {{ formatDateTime(metric?.updated_at) }}</p>
        </div>

        <div class="indicator-grid">
          <div class="indicator-card">
            <span>EMA 20</span>
            <strong>{{ formatCurrency(metric?.ema_20 ?? null) }}</strong>
          </div>
          <div class="indicator-card">
            <span>EMA 50</span>
            <strong>{{ formatCurrency(metric?.ema_50 ?? null) }}</strong>
          </div>
          <div class="indicator-card">
            <span>SMA 50</span>
            <strong>{{ formatCurrency(metric?.sma_50 ?? null) }}</strong>
          </div>
          <div class="indicator-card">
            <span>SMA 200</span>
            <strong>{{ formatCurrency(metric?.sma_200 ?? null) }}</strong>
          </div>
          <div class="indicator-card">
            <span>RSI 14</span>
            <strong>{{ metric?.rsi_14?.toFixed(2) ?? "No data" }}</strong>
          </div>
          <div class="indicator-card">
            <span>MACD Histogram</span>
            <strong>{{ metric?.macd_histogram?.toFixed(2) ?? "No data" }}</strong>
          </div>
          <div class="indicator-card">
            <span>ATR 14</span>
            <strong>{{ metric?.atr_14?.toFixed(2) ?? "No data" }}</strong>
          </div>
          <div class="indicator-card">
            <span>BB Width</span>
            <strong>{{ formatPercent((metric?.bb_width ?? null) !== null ? (metric?.bb_width ?? 0) * 100 : null) }}</strong>
          </div>
        </div>
      </article>

      <article class="surface-card">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Pattern history</p>
            <h3>Contextual pattern flow</h3>
          </div>
          <p>{{ patternSignals.length }} items</p>
        </div>

        <div v-if="patternSignals.length === 0" class="surface-state">
          No stored pattern signals for {{ symbol }} yet.
        </div>
        <ul v-else class="detail-signal-list">
          <li v-for="signal in patternSignals.slice(0, 12)" :key="signal.id">
            <div>
              <strong>{{ formatSignalType(signal.signal_type) }}</strong>
              <p>
                {{ timeframeToLabel(signal.timeframe) }} / {{ formatDateTime(signal.candle_timestamp) }}
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
    </section>

    <section class="detail-grid__row">
      <article class="surface-card">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Regime map</p>
            <h3>Per-timeframe market state</h3>
          </div>
          <p>{{ regime?.canonical_regime ? formatMarketRegime(regime.canonical_regime) : "Pending" }}</p>
        </div>

        <div v-if="!regime || regime.items.length === 0" class="surface-state">
          No regime snapshots for {{ symbol }} yet.
        </div>
        <div v-else class="indicator-grid">
          <div v-for="item in regime.items" :key="item.timeframe" class="indicator-card">
            <span>{{ timeframeToLabel(item.timeframe) }}</span>
            <strong>{{ formatMarketRegime(item.regime) }}</strong>
            <small>{{ Math.round(item.confidence * 100) }}%</small>
          </div>
        </div>
      </article>

      <article class="surface-card">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Market cycle</p>
            <h3>Macro phase context</h3>
          </div>
          <p>{{ cycles.length }} tracked phases</p>
        </div>

        <div v-if="cycles.length === 0" class="surface-state">
          No market cycle snapshots for {{ symbol }} yet.
        </div>
        <div v-else class="indicator-grid">
          <div v-for="cycle in cycles" :key="`${cycle.coin_id}-${cycle.timeframe}`" class="indicator-card">
            <span>{{ timeframeToLabel(cycle.timeframe) }}</span>
            <strong>{{ cycle.cycle_phase }}</strong>
            <small>{{ Math.round(cycle.confidence * 100) }}%</small>
          </div>
        </div>
      </article>
    </section>
  </section>
</template>
