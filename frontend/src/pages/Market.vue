<script setup lang="ts">
import { onMounted } from "vue";

import PageToolbar from "../components/layout/PageToolbar.vue";
import DashboardCrossMarketSection from "../features/dashboard/components/DashboardCrossMarketSection.vue";
import DashboardHeroSection from "../features/dashboard/components/DashboardHeroSection.vue";
import DashboardSignalsSection from "../features/dashboard/components/DashboardSignalsSection.vue";
import { useCoinStore } from "../stores/coinStore";
import { formatDateTime, formatPercent } from "../utils/format";

const coinStore = useCoinStore();

onMounted(() => {
  void coinStore.bootstrapDashboard();
});
</script>

<template>
  <section class="dashboard-grid">
    <PageToolbar title="Market">
      <template #controls>
        <button class="action-chip action-chip--compact" type="button" @click="coinStore.refreshDashboard()">
          Refresh
        </button>
      </template>

      <template #stats>
        <article class="page-toolbar__stat">
          <span>Tracked</span>
          <strong>{{ coinStore.enabledCoinsCount }}</strong>
          <small>watchlist assets</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Bullish share</span>
          <strong>{{ coinStore.bullishShare }}%</strong>
          <small>trend state split</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Signal flow</span>
          <strong>{{ coinStore.signals.length }}</strong>
          <small>{{ coinStore.topSignals.length }} ranked</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Exposure</span>
          <strong>{{ formatPercent(coinStore.portfolioExposure, 1) }}</strong>
          <small>{{ formatDateTime(coinStore.lastDashboardRefreshAt) }}</small>
        </article>
      </template>
    </PageToolbar>

    <DashboardHeroSection hide-hero />
    <DashboardSignalsSection />
    <DashboardCrossMarketSection />
  </section>
</template>
