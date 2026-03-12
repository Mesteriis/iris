<template>
  <div class="ui-chips">
    <label v-if="label" class="ui-chips__label">{{ label }}</label>
    <div class="ui-chips__box" @click="focusInput">
      <span v-for="chip in modelValue" :key="chip" class="ui-chips__item">
        {{ chip }}
        <button
          type="button"
          class="ui-chips__remove"
          @click.stop="removeChip(chip)"
        >
          ×
        </button>
      </span>
      <input
        ref="inputRef"
        class="ui-chips__input"
        type="text"
        :placeholder="placeholder"
        :value="draft"
        @input="onInput"
        @keydown.enter.prevent="commitDraft"
        @keydown="onKeydown"
        @blur="commitDraft"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";

const props = withDefaults(
  defineProps<{
    modelValue: string[];
    label?: string;
    placeholder?: string;
  }>(),
  {
    label: "",
    placeholder: "Добавьте значение",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string[]];
}>();

const draft = ref("");
const inputRef = ref<HTMLInputElement | null>(null);

function onInput(event: Event): void {
  const target = event.target as HTMLInputElement | null;
  draft.value = String(target?.value || "");
}

function commitDraft(): void {
  const value = draft.value.trim();
  if (!value) return;
  if (props.modelValue.includes(value)) {
    draft.value = "";
    return;
  }
  emit("update:modelValue", [...props.modelValue, value]);
  draft.value = "";
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== ",") return;
  event.preventDefault();
  commitDraft();
}

function removeChip(chip: string): void {
  emit(
    "update:modelValue",
    props.modelValue.filter((value) => value !== chip),
  );
}

function focusInput(): void {
  inputRef.value?.focus();
}
</script>
