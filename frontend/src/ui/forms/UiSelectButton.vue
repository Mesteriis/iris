<template>
  <div
    class="ui-select-button"
    role="group"
    :aria-label="label || 'select-button'"
    :class="{ 'is-disabled': disabled }"
  >
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="ui-select-button__item"
      :class="{ 'is-active': modelValue === option.value }"
      :disabled="disabled"
      @click="emit('update:modelValue', option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
interface UiOption {
  label: string;
  value: string;
}

defineProps<{
  modelValue: string;
  options: readonly UiOption[];
  label?: string;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();
</script>
