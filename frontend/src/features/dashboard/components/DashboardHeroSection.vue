<script setup lang="ts">
import { computed } from "vue";

import { useCoinStore } from "../../../stores/coinStore";
import {
  formatCurrency,
  formatCurrencyDelta,
  formatDateTime,
  formatMarketRegime,
  formatPercent,
  formatTrend,
} from "../../../utils/format";

const coinStore = useCoinStore();
const leadRows = computed(() => coinStore.dashboardRows.slice(0, 3));
defineProps<{
  hideHero?: boolean;
}>();
</script>

<template>
  <div v-if="!hideHero" class="hero-panel">
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
        <span>Portfolio exposure</span>
        <strong>{{ formatPercent(coinStore.portfolioExposure, 1) }}</strong>
        <small>{{ coinStore.portfolioState?.open_positions ?? 0 }} open positions</small>
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
        :to="`/assets/${row.symbol}`"
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
</template>
