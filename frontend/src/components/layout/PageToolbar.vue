<template>
  <section class="surface-card page-toolbar">
    <div class="page-toolbar__head">
      <div class="page-toolbar__title">
        <h1>{{ title }}</h1>
      </div>

      <div v-if="$slots.controls" class="page-toolbar__controls">
        <slot name="controls" />
      </div>
    </div>

    <div v-if="$slots.stats" class="page-toolbar__stats">
      <slot name="stats" />
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
}>();
</script>
