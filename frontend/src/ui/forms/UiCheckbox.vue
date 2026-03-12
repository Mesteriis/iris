<template>
  <label class="ui-checkbox" :class="{ 'is-disabled': disabled }">
    <input
      class="ui-checkbox__input"
      type="checkbox"
      :checked="modelValue"
      :disabled="disabled"
      @change="onChange"
    />
    <span class="ui-checkbox__box" aria-hidden="true" />
    <span class="ui-checkbox__label"
      ><slot>{{ label }}</slot></span
    >
  </label>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: boolean;
  label?: string;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

function onChange(event: Event): void {
  const target = event.target as HTMLInputElement | null;
  emit("update:modelValue", Boolean(target?.checked));
}
</script>
