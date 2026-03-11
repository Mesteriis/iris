<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute } from "vue-router";

import { useCoinStore } from "../../stores/coinStore";
import {
  formatCompactNumber,
  formatDurationSeconds,
  formatCurrencyDelta,
  formatDateTime,
  formatRateLimitPolicy,
  formatSignalType,
  timeframeToLabel,
} from "../../utils/format";

const route = useRoute();
const coinStore = useCoinStore();
const sidebarOpen = ref(false);

const pageTitle = computed(() => {
  if (route.name === "coin-history") {
    return `${String(route.params.symbol || "").toUpperCase()} analysis desk`;
  }

  return "Long-horizon market board";
});

const pageSubtitle = computed(() => {
  if (route.name === "coin-history") {
    return "Trend structure, regime state and event flow from precomputed analytics.";
  }

  return "IRIS reads precomputed metrics, signals and candle history without scanning raw tables in the UI.";
});

const systemBadge = computed(() => {
  if (coinStore.status?.status === "ok" && coinStore.status.taskiq_running) {
    return "Live";
  }

  if (coinStore.isBootstrapping) {
    return "Syncing";
  }

  return "Degraded";
});

const sidebarSignals = computed(() => coinStore.recentSignals.slice(0, 6));
const sidebarRows = computed(() => coinStore.dashboardRows.slice(0, 5));
const sidebarJobs = computed(() => coinStore.jobStatusRows.slice(0, 6));
const sidebarSources = computed(() => coinStore.sourceStatusRows.slice(0, 6));

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value;
}
</script>

<template>
  <main class="iris-shell" :class="{ 'sidebar-open': sidebarOpen }">
    <aside class="iris-sidebar">
      <div class="iris-sidebar__backdrop" />

      <section class="iris-brand">
        <div class="iris-brand__badge">IR</div>
        <div>
          <p class="iris-brand__title">IRIS</p>
          <p class="iris-brand__subtitle">market intelligence shell</p>
        </div>
      </section>

      <nav class="iris-nav" aria-label="Primary">
        <RouterLink class="iris-nav__link" :class="{ 'is-active': route.name === 'coins' }" to="/">
          <span>Overview</span>
          <small>{{ coinStore.enabledCoinsCount }} active</small>
        </RouterLink>
        <RouterLink
          v-if="route.name === 'coin-history'"
          class="iris-nav__link is-active"
          :to="route.fullPath"
        >
          <span>{{ String(route.params.symbol || "").toUpperCase() }}</span>
          <small>Detail desk</small>
        </RouterLink>
      </nav>

      <section class="iris-sidebar__panel">
        <div class="panel-heading">
          <span>System state</span>
          <span class="status-pill" :class="`status-pill--${coinStore.statusTone}`">{{ systemBadge }}</span>
        </div>
        <dl class="system-grid">
          <div>
            <dt>Backend</dt>
            <dd>{{ coinStore.status?.service ?? "IRIS" }}</dd>
          </div>
          <div>
            <dt>TaskIQ</dt>
            <dd>{{ coinStore.status?.taskiq_running ? "Embedded" : "Down" }}</dd>
          </div>
          <div>
            <dt>Metrics rows</dt>
            <dd>{{ coinStore.metrics.length }}</dd>
          </div>
          <div>
            <dt>Last refresh</dt>
            <dd>{{ formatDateTime(coinStore.lastDashboardRefreshAt) }}</dd>
          </div>
        </dl>
      </section>

      <section class="iris-sidebar__panel">
        <div class="panel-heading">
          <span>Source limits</span>
          <span>{{ coinStore.sourceStatusCounts.rateLimited }}/{{ coinStore.sourceStatusCounts.total }}</span>
        </div>
        <ul class="watchlist">
          <li v-for="source in sidebarSources" :key="source.name">
            <div class="watchlist__item watchlist__item--static">
              <div>
                <strong>{{ source.name }}</strong>
                <p>{{ formatRateLimitPolicy(source.requests_per_window, source.window_seconds, source.request_cost) }}</p>
              </div>
              <div class="watchlist__meta">
                <span class="source-badge" :class="`source-badge--${source.rate_limited ? 'limited' : 'live'}`">
                  {{ source.rate_limited ? "Cooling" : "Live" }}
                </span>
                <small>
                  {{ source.rate_limited ? formatDurationSeconds(source.cooldown_seconds) : (source.min_interval_seconds ? `${source.min_interval_seconds}s gap` : "Open") }}
                </small>
              </div>
            </div>
          </li>
        </ul>
      </section>

      <section class="iris-sidebar__panel">
        <div class="panel-heading">
          <span>Signal stream</span>
          <span>{{ coinStore.signals.length }}</span>
        </div>
        <ul class="signal-stream">
          <li v-for="signal in sidebarSignals" :key="`${signal.symbol}-${signal.signal_type}-${signal.candle_timestamp}`">
            <RouterLink class="signal-stream__item" :to="`/coins/${signal.symbol}`">
              <div>
                <strong>{{ signal.symbol }}</strong>
                <p>{{ formatSignalType(signal.signal_type) }}</p>
              </div>
              <div class="signal-stream__meta">
                <span>{{ timeframeToLabel(signal.timeframe) }}</span>
                <small>{{ Math.round(signal.confidence * 100) }}%</small>
              </div>
            </RouterLink>
          </li>
        </ul>
      </section>

      <section class="iris-sidebar__panel">
        <div class="panel-heading">
          <span>High conviction</span>
          <span>Top 5</span>
        </div>
        <ul class="watchlist">
          <li v-for="row in sidebarRows" :key="row.symbol">
            <RouterLink class="watchlist__item" :to="`/coins/${row.symbol}`">
              <div>
                <strong>{{ row.symbol }}</strong>
                <p>{{ row.name }}</p>
              </div>
              <div class="watchlist__meta">
                <span>{{ row.trend_score ?? "NA" }}</span>
                <small>{{ formatCurrencyDelta(row.price_change_24h) }}</small>
              </div>
            </RouterLink>
          </li>
        </ul>
      </section>

      <section class="iris-sidebar__panel">
        <div class="panel-heading">
          <span>Job status</span>
          <span>{{ coinStore.jobStatusRows.length }}</span>
        </div>
        <ul class="watchlist">
          <li v-for="entry in sidebarJobs" :key="entry.coin.symbol">
            <RouterLink class="watchlist__item" :to="`/coins/${entry.coin.symbol}`">
              <div>
                <strong>{{ entry.coin.symbol }}</strong>
                <p>{{ entry.job.label }}</p>
              </div>
              <div class="watchlist__meta">
                <span class="job-badge" :class="`job-badge--${entry.job.state}`">{{ entry.job.label }}</span>
                <small>{{ formatDateTime(entry.job.timestamp) }}</small>
              </div>
            </RouterLink>
          </li>
        </ul>
      </section>
    </aside>

    <div class="iris-main">
      <header class="iris-header">
        <button class="iris-mobile-toggle" type="button" @click="toggleSidebar">
          {{ sidebarOpen ? "Close" : "Menu" }}
        </button>

        <div>
          <p class="iris-header__eyebrow">IRIS / Analytics</p>
          <h1 class="iris-header__title">{{ pageTitle }}</h1>
          <p class="iris-header__subtitle">{{ pageSubtitle }}</p>
        </div>

        <div class="iris-header__actions">
          <button class="action-chip" type="button" @click="coinStore.refreshDashboard()">
            Refresh
          </button>
          <div class="action-card">
            <span>Tracked</span>
            <strong>{{ formatCompactNumber(coinStore.enabledCoinsCount) }}</strong>
          </div>
          <div class="action-card">
            <span>Signals</span>
            <strong>{{ formatCompactNumber(coinStore.signals.length) }}</strong>
          </div>
        </div>
      </header>

      <section class="iris-canvas">
        <slot />
      </section>
    </div>
  </main>
</template>
