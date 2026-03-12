<template>
  <header class="hero-glass-tabs-shell">
    <div class="hero-glass-tabs-bg" aria-hidden="true">
      <img :src="emblemSrc" alt="" />
    </div>

    <div class="hero-glass-tabs-main">
      <slot />
    </div>

    <div v-if="$slots.actions" class="hero-glass-tabs-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  emblemSrc: string;
}>();
</script>
