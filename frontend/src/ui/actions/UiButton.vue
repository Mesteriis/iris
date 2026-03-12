<template>
  <button
    class="ui-btn"
    :class="[
      `ui-btn--${variant}`,
      `ui-btn--${size}`,
      { 'is-loading': loading, 'is-block': block },
    ]"
    :type="type"
    :disabled="disabled || loading"
    @click="onClick"
  >
    <span v-if="$slots.icon && iconPosition === 'left'" class="ui-btn__icon">
      <slot name="icon" />
    </span>
    <span class="ui-btn__label"
      ><slot>{{ label }}</slot></span
    >
    <span v-if="$slots.icon && iconPosition === 'right'" class="ui-btn__icon">
      <slot name="icon" />
    </span>
  </button>
</template>

<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    label?: string;
    variant?: "primary" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md" | "lg";
    type?: "button" | "submit" | "reset";
    disabled?: boolean;
    loading?: boolean;
    block?: boolean;
    iconPosition?: "left" | "right";
  }>(),
  {
    label: "",
    variant: "primary",
    size: "md",
    type: "button",
    disabled: false,
    loading: false,
    block: false,
    iconPosition: "left",
  },
);

const emit = defineEmits<{
  click: [event: MouseEvent];
}>();

function onClick(event: MouseEvent): void {
  if (props.disabled || props.loading) {
    event.preventDefault();
    return;
  }
  emit("click", event);
}
</script>
