<script setup lang="ts">
defineProps<{
  kind: "all" | "commodity" | "crypto" | "energy" | "equity" | "forex" | "index" | "metal" | "generic";
}>();
</script>

<template>
  <svg class="asset-type-icon" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <template v-if="kind === 'all'">
      <rect x="2.9" y="2.9" width="4.1" height="4.1" rx="0.9" />
      <rect x="9" y="2.9" width="4.1" height="4.1" rx="0.9" />
      <rect x="2.9" y="9" width="4.1" height="4.1" rx="0.9" />
      <rect x="9" y="9" width="4.1" height="4.1" rx="0.9" />
    </template>
    <template v-else-if="kind === 'crypto'">
      <path d="M8 2.6 12.4 5v6L8 13.4 3.6 11V5L8 2.6Z" />
      <path d="M8 5.3 10.4 8 8 10.7 5.6 8 8 5.3Z" />
    </template>
    <template v-else-if="kind === 'equity'">
      <path d="M3.8 12.2V8.8" />
      <path d="M8 12.2V4.2" />
      <path d="M12.2 12.2V6.5" />
    </template>
    <template v-else-if="kind === 'forex'">
      <path d="M3.2 5.4h7" />
      <path d="m8.1 3.3 2.3 2.1-2.3 2.1" />
      <path d="M12.8 10.6h-7" />
      <path d="m7.9 8.5-2.3 2.1 2.3 2.1" />
    </template>
    <template v-else-if="kind === 'energy'">
      <path d="M8.8 2.8 5.3 8h2.2L7 13.2l3.7-5.3H8.4l.4-5.1Z" />
    </template>
    <template v-else-if="kind === 'metal' || kind === 'commodity'">
      <path d="M4.1 4.6h7.8" />
      <path d="M3 8h10" />
      <path d="M4.8 11.4h6.4" />
    </template>
    <template v-else-if="kind === 'index'">
      <rect x="3.4" y="3.4" width="3.3" height="3.3" rx="0.8" />
      <rect x="9.3" y="3.4" width="3.3" height="3.3" rx="0.8" />
      <rect x="3.4" y="9.3" width="3.3" height="3.3" rx="0.8" />
      <rect x="9.3" y="9.3" width="3.3" height="3.3" rx="0.8" />
    </template>
    <template v-else>
      <circle cx="8" cy="8" r="3.2" />
      <path d="M8 2.7v1.2" />
      <path d="M8 12.1v1.2" />
      <path d="M2.7 8h1.2" />
      <path d="M12.1 8h1.2" />
    </template>
  </svg>
</template>
