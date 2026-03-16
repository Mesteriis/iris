import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { irisApi, type Coin, type SystemStatus } from "../services/api";
import { getCoinJobSnapshot } from "../utils/coinJobs";

export const useShellStore = defineStore("shell", () => {
  const coins = ref<Coin[]>([]);
  const status = ref<SystemStatus | null>(null);
  const loading = ref(false);
  const error = ref("");
  const lastUpdatedAt = ref<string | null>(null);

  const runtimeOnline = computed(() => status.value?.status === "ok" && status.value.taskiq_running);
  const trackedAssets = computed(() => coins.value.filter((coin) => coin.enabled).length);
  const backgroundJobs = computed(() =>
    coins.value.reduce((total, coin) => {
      const state = getCoinJobSnapshot(coin).state;
      return total + (state === "backfilling" || state === "queued" || state === "retry_scheduled" ? 1 : 0);
    }, 0),
  );
  const coolingSources = computed(() => status.value?.sources.filter((source) => source.rate_limited).length ?? 0);
  const errorJobs = computed(() =>
    coins.value.reduce((total, coin) => total + (getCoinJobSnapshot(coin).state === "error" ? 1 : 0), 0),
  );

  async function refresh() {
    loading.value = true;
    error.value = "";
    try {
      const snapshot = await irisApi.getFrontendShellSnapshot();
      status.value = snapshot.status;
      coins.value = snapshot.coins;
      lastUpdatedAt.value = new Date().toISOString();
    } catch (nextError) {
      error.value = nextError instanceof Error ? nextError.message : "Failed to refresh shell runtime state.";
    } finally {
      loading.value = false;
    }
  }

  async function bootstrap() {
    if (status.value && coins.value.length > 0) {
      return;
    }
    await refresh();
  }

  return {
    backgroundJobs,
    bootstrap,
    coins,
    coolingSources,
    error,
    errorJobs,
    lastUpdatedAt,
    loading,
    refresh,
    runtimeOnline,
    status,
    trackedAssets,
  };
});
