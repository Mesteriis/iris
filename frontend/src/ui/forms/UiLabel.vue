<template>
  <label class="ui-label" :for="forId">
    <span class="ui-label__text">
      <slot>{{ text }}</slot>
      <sup v-if="required" class="ui-label__required">*</sup>
    </span>
    <small v-if="hint" class="ui-label__hint">{{ hint }}</small>
  </label>
</template>

<script setup lang="ts">
defineProps<{
  text?: string;
  hint?: string;
  forId?: string;
  required?: boolean;
}>();
</script>
