<script setup lang="ts">
import { onMounted } from "vue";

import PageToolbar from "../components/layout/PageToolbar.vue";
import DashboardPortfolioSection from "../features/dashboard/components/DashboardPortfolioSection.vue";
import { useCoinStore } from "../stores/coinStore";
import { formatCurrency, formatDateTime, formatPercent } from "../utils/format";

const coinStore = useCoinStore();

onMounted(() => {
  void coinStore.bootstrapDashboard();
});
</script>

<template>
  <section class="dashboard-grid">
    <PageToolbar title="Portfolio">
      <template #controls>
        <button class="action-chip action-chip--compact" type="button" @click="coinStore.refreshDashboard()">
          Refresh
        </button>
      </template>

      <template #stats>
        <article class="page-toolbar__stat">
          <span>Total capital</span>
          <strong>{{ formatCurrency(coinStore.portfolioState?.total_capital ?? null) }}</strong>
          <small>{{ coinStore.portfolioState?.open_positions ?? 0 }} open</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Allocated</span>
          <strong>{{ formatCurrency(coinStore.portfolioState?.allocated_capital ?? null) }}</strong>
          <small>{{ formatPercent(coinStore.portfolioExposure, 1) }} exposure</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Unrealized</span>
          <strong :class="{ positive: coinStore.portfolioPnl > 0, negative: coinStore.portfolioPnl < 0 }">
            {{ formatCurrency(coinStore.portfolioPnl) }}
          </strong>
          <small>live P/L</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Updated</span>
          <strong>{{ formatDateTime(coinStore.portfolioState?.updated_at ?? coinStore.lastDashboardRefreshAt) }}</strong>
          <small>{{ coinStore.latestPortfolioActions.length }} latest actions</small>
        </article>
      </template>
    </PageToolbar>

    <DashboardPortfolioSection />
  </section>
</template>
