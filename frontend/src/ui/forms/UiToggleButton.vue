<template>
  <button
    class="ui-toggle-btn"
    :class="{ 'is-active': modelValue }"
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :disabled="disabled"
    @click="toggle"
  >
    <span class="ui-toggle-btn__dot" />
    <span class="ui-toggle-btn__label">{{
      modelValue ? onLabel : offLabel
    }}</span>
  </button>
</template>

<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    onLabel?: string;
    offLabel?: string;
    disabled?: boolean;
  }>(),
  {
    onLabel: "ON",
    offLabel: "OFF",
    disabled: false,
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  change: [value: boolean];
}>();

function toggle(): void {
  if (props.disabled) return;
  const nextValue = !props.modelValue;
  emit("update:modelValue", nextValue);
  emit("change", nextValue);
}
</script>
