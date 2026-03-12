<template>
  <div
    ref="rootRef"
    class="ui-select"
    :class="{
      'is-open': open,
      'is-multiple': multiple,
      'is-searchable': search,
      'is-disabled': disabled,
    }"
  >
    <label v-if="label" class="ui-select__label">{{ label }}</label>

    <button
      :id="id"
      type="button"
      class="ui-select__trigger"
      :disabled="disabled"
      :aria-expanded="open"
      :aria-haspopup="'listbox'"
      @click="toggleOpen"
    >
      <slot
        name="trigger"
        :open="open"
        :selected-label="selectedLabel"
        :selected-labels="selectedLabels"
        :display-value="displayValue"
      >
        <span v-if="displayValue" class="ui-select__value">{{
          displayValue
        }}</span>
        <span v-else class="ui-select__placeholder">{{ placeholder }}</span>
        <span class="ui-select__caret" aria-hidden="true">▾</span>
      </slot>
    </button>

    <transition name="ui-control-pop">
      <div
        v-if="open"
        class="ui-select__panel"
        role="listbox"
        :aria-multiselectable="multiple ? 'true' : undefined"
      >
        <div v-if="search" class="ui-select__search-wrap">
          <input
            ref="searchInputRef"
            class="ui-select__search-input"
            type="search"
            :placeholder="searchPlaceholder"
            :value="query"
            @input="onSearchInput"
          />
        </div>

        <button
          v-if="allowEmptyOption"
          type="button"
          class="ui-select__option"
          :class="{ 'is-active': !selectedValues.length }"
          role="option"
          :aria-selected="!selectedValues.length"
          @click="selectSingleValue('')"
        >
          {{ placeholder }}
        </button>

        <button
          v-for="option in filteredOptions"
          :key="option.value"
          type="button"
          class="ui-select__option"
          :class="{
            'is-active': isSelected(option.value),
            'is-disabled': option.disabled,
          }"
          role="option"
          :aria-selected="isSelected(option.value)"
          :disabled="option.disabled"
          @click="toggleOption(option)"
        >
          <slot
            name="option"
            :option="option"
            :selected="isSelected(option.value)"
            :toggle="() => toggleOption(option)"
          >
            <span>{{ option.label }}</span>
            <span v-if="multiple" class="ui-select__check">{{
              isSelected(option.value) ? "✓" : ""
            }}</span>
          </slot>
        </button>

        <p v-if="!filteredOptions.length" class="ui-select__empty">
          <slot name="empty">Ничего не найдено</slot>
        </p>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";

interface UiOption {
  label: string;
  value: string;
  disabled?: boolean;
}

type UiSelectModel = string | string[];

const props = withDefaults(
  defineProps<{
    id?: string;
    label?: string;
    modelValue: UiSelectModel;
    options: UiOption[];
    placeholder?: string;
    disabled?: boolean;
    multiple?: boolean;
    search?: boolean;
    searchPlaceholder?: string;
  }>(),
  {
    id: "",
    label: "",
    placeholder: "Выберите",
    disabled: false,
    multiple: false,
    search: false,
    searchPlaceholder: "Поиск...",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: UiSelectModel];
  open: [];
  close: [];
  search: [value: string];
}>();

const open = ref(false);
const query = ref("");
const rootRef = ref<HTMLElement | null>(null);
const searchInputRef = ref<HTMLInputElement | null>(null);

const selectedValues = computed<string[]>(() => {
  if (props.multiple) {
    if (!Array.isArray(props.modelValue)) return [];
    return props.modelValue.map((value) => String(value || ""));
  }
  if (Array.isArray(props.modelValue)) {
    return props.modelValue.length ? [String(props.modelValue[0] || "")] : [];
  }
  const value = String(props.modelValue || "");
  return value ? [value] : [];
});

const selectedLabels = computed(() => {
  const selectedSet = new Set(selectedValues.value);
  return props.options
    .filter((option) => selectedSet.has(option.value))
    .map((option) => option.label);
});

const selectedLabel = computed(() => selectedLabels.value[0] || "");
const displayValue = computed(() =>
  props.multiple ? selectedLabels.value.join(", ") : selectedLabel.value,
);

const allowEmptyOption = computed(
  () => !props.multiple && Boolean(props.placeholder),
);

const filteredOptions = computed(() => {
  const normalized = query.value.trim().toLowerCase();
  if (!props.search || !normalized) return props.options;
  return props.options.filter((option) =>
    option.label.toLowerCase().includes(normalized),
  );
});

watch(
  () => open.value,
  (isOpen) => {
    if (isOpen) {
      emit("open");
      if (props.search) {
        void nextTick(() => {
          searchInputRef.value?.focus();
        });
      }
      return;
    }
    query.value = "";
    emit("close");
  },
);

function toggleOpen(): void {
  if (props.disabled) return;
  open.value = !open.value;
}

function isSelected(value: string): boolean {
  return selectedValues.value.includes(value);
}

function selectSingleValue(value: string): void {
  emit("update:modelValue", value);
  open.value = false;
}

function toggleOption(option: UiOption): void {
  if (option.disabled) return;

  if (!props.multiple) {
    selectSingleValue(option.value);
    return;
  }

  const next = new Set(selectedValues.value);
  if (next.has(option.value)) {
    next.delete(option.value);
  } else {
    next.add(option.value);
  }
  emit("update:modelValue", Array.from(next));
}

function onSearchInput(event: Event): void {
  const target = event.target as HTMLInputElement | null;
  query.value = String(target?.value || "");
  emit("search", query.value);
}

function closeOnOutsideClick(event: PointerEvent): void {
  if (!open.value) return;
  const target = event.target as Node | null;
  if (target && rootRef.value?.contains(target)) return;
  open.value = false;
}

function closeOnEscape(event: KeyboardEvent): void {
  if (!open.value) return;
  if (event.key !== "Escape") return;
  open.value = false;
}

onMounted(() => {
  window.addEventListener("pointerdown", closeOnOutsideClick);
  window.addEventListener("keydown", closeOnEscape);
});

onBeforeUnmount(() => {
  window.removeEventListener("pointerdown", closeOnOutsideClick);
  window.removeEventListener("keydown", closeOnEscape);
});
</script>
