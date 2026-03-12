<template>
  <div class="ui-input-group" :class="{ 'has-error': Boolean(error) }">
    <label v-if="label" class="ui-input-group__label" :for="id">{{
      label
    }}</label>
    <div class="ui-input-group__field-wrap">
      <span v-if="$slots.prefix || prefix" class="ui-input-group__addon">
        <slot name="prefix">{{ prefix }}</slot>
      </span>
      <input
        :id="id"
        class="ui-input-group__field"
        :type="type"
        :placeholder="placeholder"
        :value="modelValue"
        :disabled="disabled"
        @input="onInput"
        @focus="emit('focus', $event)"
        @blur="emit('blur', $event)"
      />
      <span v-if="$slots.suffix || suffix" class="ui-input-group__addon">
        <slot name="suffix">{{ suffix }}</slot>
      </span>
    </div>
    <small v-if="error" class="ui-input-group__error">{{ error }}</small>
    <small v-else-if="hint" class="ui-input-group__hint">{{ hint }}</small>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    id?: string;
    modelValue: string;
    label?: string;
    placeholder?: string;
    type?: string;
    hint?: string;
    error?: string;
    disabled?: boolean;
    prefix?: string;
    suffix?: string;
  }>(),
  {
    id: "",
    label: "",
    placeholder: "",
    type: "text",
    hint: "",
    error: "",
    disabled: false,
    prefix: "",
    suffix: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  focus: [event: FocusEvent];
  blur: [event: FocusEvent];
}>();

function onInput(event: Event): void {
  const target = event.target as HTMLInputElement | null;
  emit("update:modelValue", String(target?.value || ""));
}
</script>
