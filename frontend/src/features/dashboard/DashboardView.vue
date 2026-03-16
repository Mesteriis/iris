<script setup lang="ts">
import { onMounted } from "vue";

import { useCoinStore } from "../../stores/coinStore";
import DashboardCoverageSection from "./components/DashboardCoverageSection.vue";
import DashboardCrossMarketSection from "./components/DashboardCrossMarketSection.vue";
import DashboardHeroSection from "./components/DashboardHeroSection.vue";
import DashboardOperationsSection from "./components/DashboardOperationsSection.vue";
import DashboardPortfolioSection from "./components/DashboardPortfolioSection.vue";
import DashboardResearchSection from "./components/DashboardResearchSection.vue";
import DashboardSignalsSection from "./components/DashboardSignalsSection.vue";

const coinStore = useCoinStore();

onMounted(() => {
  void coinStore.bootstrapDashboard();
});
</script>

<template>
  <section class="dashboard-grid">
    <DashboardHeroSection />
    <DashboardPortfolioSection />
    <DashboardCrossMarketSection />
    <DashboardOperationsSection />
    <DashboardSignalsSection />
    <DashboardResearchSection />
    <DashboardCoverageSection />
  </section>
</template>
