<template>
  <label class="ui-radio" :class="{ 'is-disabled': disabled }">
    <input
      class="ui-radio__input"
      type="radio"
      :name="name"
      :value="value"
      :checked="modelValue === value"
      :disabled="disabled"
      @change="onChange"
    />
    <span class="ui-radio__dot" aria-hidden="true" />
    <span class="ui-radio__label"
      ><slot>{{ label }}</slot></span
    >
  </label>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: string;
  value: string;
  name: string;
  label?: string;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

function onChange(event: Event): void {
  const target = event.target as HTMLInputElement | null;
  emit("update:modelValue", String(target?.value || ""));
}
</script>
