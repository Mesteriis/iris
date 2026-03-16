<script setup lang="ts">
import { useCoinStore } from "../../../stores/coinStore";
import {
  formatCompactNumber,
  formatCurrency,
  formatCurrencyDelta,
  formatDateTime,
  formatMarketRegime,
  formatTrend,
} from "../../../utils/format";

const coinStore = useCoinStore();

async function runCoinJob(symbol: string) {
  await coinStore.runCoinJob(symbol, "auto", true);
}
</script>

<template>
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
              <RouterLink class="action-chip" :to="`/assets/${row.symbol}`">Open</RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
