<template>
  <section class="hero-layout">
    <header class="hero panel hero-title-panel">
      <div class="hero-title-content">
        <slot name="title" />
      </div>
    </header>

    <aside
      class="panel hero-control-panel"
      :class="[controlsClass, { active }]"
    >
      <slot name="controls" />
    </aside>
  </section>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    active?: boolean;
    controlsClass?: string;
  }>(),
  {
    active: false,
    controlsClass: "service-hero-controls",
  },
);
</script>
