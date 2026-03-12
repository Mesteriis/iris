<template>
  <button
    class="base-switch"
    :class="{ checked: modelValue, disabled }"
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :disabled="disabled"
    @click="toggle"
  >
    <span class="base-switch-track" aria-hidden="true">
      <span class="base-switch-thumb"></span>
    </span>
    <span class="base-switch-label">
      <slot>{{ label }}</slot>
    </span>
  </button>
</template>

<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    disabled?: boolean;
    label?: string;
  }>(),
  {
    disabled: false,
    label: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

function toggle(): void {
  if (props.disabled) return;
  emit("update:modelValue", !props.modelValue);
}
</script>

<style scoped>
.base-switch {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  border: 0;
  margin: 0;
  padding: 0;
  background: transparent;
  color: #d8e8f7;
  font: inherit;
  font-size: 0.82rem;
  font-weight: 620;
  cursor: pointer;
  user-select: none;
}

.base-switch:disabled,
.base-switch.disabled {
  opacity: 0.56;
  cursor: not-allowed;
}

.base-switch-track {
  position: relative;
  width: 42px;
  height: 24px;
  border: 1px solid rgba(118, 176, 201, 0.42);
  border-radius: 999px;
  background: linear-gradient(
    160deg,
    rgba(12, 27, 42, 0.92),
    rgba(9, 20, 34, 0.82)
  );
  box-shadow: inset 0 1px 0 rgba(190, 216, 232, 0.08);
  transition:
    border-color 170ms ease,
    background 170ms ease,
    box-shadow 170ms ease;
}

.base-switch-thumb {
  position: absolute;
  left: 3px;
  top: 50%;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: linear-gradient(
    180deg,
    rgba(226, 239, 252, 0.98),
    rgba(171, 199, 219, 0.94)
  );
  box-shadow: 0 2px 8px rgba(2, 10, 18, 0.45);
  transform: translateY(-50%);
  transition:
    transform 180ms cubic-bezier(0.16, 0.84, 0.3, 1),
    background 170ms ease;
}

.base-switch.checked .base-switch-track {
  border-color: rgba(110, 244, 220, 0.76);
  background: linear-gradient(
    160deg,
    rgba(27, 91, 93, 0.92),
    rgba(14, 50, 58, 0.86)
  );
  box-shadow:
    inset 0 1px 0 rgba(210, 255, 245, 0.14),
    0 0 0 1px rgba(110, 244, 220, 0.22);
}

.base-switch.checked .base-switch-thumb {
  transform: translate(18px, -50%);
  background: linear-gradient(
    180deg,
    rgba(225, 255, 248, 0.98),
    rgba(155, 248, 227, 0.95)
  );
}

.base-switch:not(.disabled):hover .base-switch-track {
  border-color: rgba(141, 220, 236, 0.62);
}

.base-switch:not(.disabled):focus-visible {
  outline: none;
}

.base-switch:not(.disabled):focus-visible .base-switch-track {
  box-shadow:
    inset 0 1px 0 rgba(210, 255, 245, 0.14),
    0 0 0 3px rgba(80, 214, 195, 0.25);
}

.base-switch-label {
  line-height: 1.2;
}
</style>
