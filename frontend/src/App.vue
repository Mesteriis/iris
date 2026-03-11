<script setup lang="ts">
import { onMounted } from "vue";

import UiBlankLayout from "./components/layout/UiBlankLayout.vue";
import { useCoinStore } from "./stores/coinStore";

const coinStore = useCoinStore();

onMounted(() => {
  void coinStore.bootstrapDashboard();
});
</script>

<template>
  <UiBlankLayout>
    <main class="iris-page">
      <RouterView />
    </main>
  </UiBlankLayout>
</template>
