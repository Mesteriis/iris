<script setup lang="ts">
import { onMounted } from "vue";

import PageToolbar from "../components/layout/PageToolbar.vue";
import DashboardResearchSection from "../features/dashboard/components/DashboardResearchSection.vue";
import { useCoinStore } from "../stores/coinStore";

const coinStore = useCoinStore();

onMounted(() => {
  void coinStore.bootstrapDashboard();
});
</script>

<template>
  <section class="dashboard-grid">
    <PageToolbar title="Research">
      <template #controls>
        <button class="action-chip action-chip--compact" type="button" @click="coinStore.refreshDashboard()">
          Refresh
        </button>
      </template>

      <template #stats>
        <article class="page-toolbar__stat">
          <span>Strategies</span>
          <strong>{{ coinStore.strategies.length }}</strong>
          <small>{{ coinStore.topStrategies.length }} ranked</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Patterns</span>
          <strong>{{ coinStore.activePatternsCount }}</strong>
          <small>{{ coinStore.disabledPatternsCount }} disabled</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Backtests</span>
          <strong>{{ coinStore.topBacktests.length }}</strong>
          <small>ranked signal stacks</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Discovery</span>
          <strong>{{ coinStore.discoveredPatterns.length }}</strong>
          <small>review candidates</small>
        </article>
      </template>
    </PageToolbar>

    <DashboardResearchSection />
  </section>
</template>
