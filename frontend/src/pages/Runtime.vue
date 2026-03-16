<script setup lang="ts">
import { computed, onMounted } from "vue";

import PageToolbar from "../components/layout/PageToolbar.vue";
import DashboardOperationsSection from "../features/dashboard/components/DashboardOperationsSection.vue";
import HypothesisAiStreamPanel from "../features/runtime/HypothesisAiStreamPanel.vue";
import { useCoinStore } from "../stores/coinStore";
import { formatDateTime } from "../utils/format";

const coinStore = useCoinStore();

const activeJobsCount = computed(
  () => coinStore.jobStatusCounts.backfilling + coinStore.jobStatusCounts.queued + coinStore.jobStatusCounts.retry_scheduled,
);
const coolingSources = computed(() => coinStore.sourceStatusCounts.rateLimited);

onMounted(() => {
  void coinStore.bootstrapDashboard();
});
</script>

<template>
  <section class="dashboard-grid">
    <PageToolbar title="Runtime">
      <template #controls>
        <button class="action-chip action-chip--compact" type="button" @click="coinStore.refreshDashboard()">
          Refresh
        </button>
      </template>

      <template #stats>
        <article class="page-toolbar__stat">
          <span>Runtime</span>
          <strong>{{ coinStore.status?.status ?? "—" }}</strong>
          <small>{{ coinStore.status?.taskiq_running ? "workers online" : "workers idle" }}</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Jobs</span>
          <strong>{{ activeJobsCount }}</strong>
          <small>{{ coinStore.jobStatusCounts.error }} sync errors</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Cooling</span>
          <strong>{{ coolingSources }}</strong>
          <small>{{ coinStore.sourceStatusCounts.total }} providers</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Updated</span>
          <strong>{{ formatDateTime(coinStore.lastDashboardRefreshAt) }}</strong>
          <small>runtime snapshot</small>
        </article>
      </template>
    </PageToolbar>

    <HypothesisAiStreamPanel />
    <DashboardOperationsSection />
  </section>
</template>
