<template>
  <button
    class="ghost icon-btn"
    :class="[buttonClass, { active }]"
    :type="type"
    :title="title"
    :aria-label="ariaLabel || title"
    :disabled="disabled"
    @click="emitClick"
  >
    <slot />
  </button>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    active?: boolean;
    disabled?: boolean;
    type?: "button" | "submit" | "reset";
    title?: string;
    ariaLabel?: string;
    buttonClass?: string;
  }>(),
  {
    active: false,
    disabled: false,
    type: "button",
    title: "",
    ariaLabel: "",
    buttonClass: "",
  },
);

const emit = defineEmits<{
  click: [event: MouseEvent];
}>();

function emitClick(event: MouseEvent): void {
  emit("click", event);
}
</script>
