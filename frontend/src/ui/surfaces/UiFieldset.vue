<template>
  <fieldset class="ui-fieldset" :class="{ 'is-collapsible': collapsible }">
    <legend>
      <button
        v-if="collapsible"
        type="button"
        class="ui-fieldset__toggle"
        @click="toggle"
      >
        <span>{{ legend }}</span>
        <span>{{ isOpen ? "▾" : "▸" }}</span>
      </button>
      <span v-else>{{ legend }}</span>
    </legend>

    <div v-if="isOpen" class="ui-fieldset__content">
      <slot />
    </div>
  </fieldset>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    legend: string;
    collapsible?: boolean;
    modelValue?: boolean;
  }>(),
  {
    collapsible: false,
    modelValue: true,
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

const isOpen = computed(() =>
  props.collapsible ? Boolean(props.modelValue) : true,
);

function toggle(): void {
  if (!props.collapsible) return;
  emit("update:modelValue", !props.modelValue);
}
</script>
