<template>
  <div
    class="ui-divider"
    :class="`orientation-${orientation}`"
    role="separator"
  >
    <span v-if="label" class="ui-divider__label">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    label?: string;
    orientation?: "horizontal" | "vertical";
  }>(),
  {
    label: "",
    orientation: "horizontal",
  },
);
</script>
