<template>
  <button
    v-bind="attrs"
    class="tree-node ui-sidebar-list-item"
    :class="[variantClass, { active }]"
    type="button"
    @click="emit('click', $event)"
  >
    <slot />
  </button>
</template>

<script setup lang="ts">
import { computed, useAttrs } from "vue";

defineOptions({
  inheritAttrs: false,
});

const props = withDefaults(
  defineProps<{
    active?: boolean;
    variant?: "default" | "group" | "subgroup" | "item";
  }>(),
  {
    active: false,
    variant: "default",
  },
);

const emit = defineEmits<{
  click: [MouseEvent];
}>();

const attrs = useAttrs();

const variantClass = computed(() => {
  if (props.variant === "default") return "";
  return `tree-${props.variant}`;
});
</script>
