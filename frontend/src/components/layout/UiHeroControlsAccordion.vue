<template>
  <div class="hero-controls-content">
    <div class="hero-controls-accordion" :class="{ open: isOpen }">
      <Transition name="hero-controls-drawer-transition">
        <div v-if="isOpen" :id="drawerId" class="hero-controls-drawer">
          <slot name="drawer" />
        </div>
      </Transition>

      <button
        class="hero-controls-trigger"
        type="button"
        :aria-expanded="isOpen"
        :aria-controls="drawerId"
        :title="isOpen ? collapseTitle : expandTitle"
        @click="isOpen = !isOpen"
      >
        <span
          class="ui-icon hero-accordion-caret"
          :class="{ open: isOpen }"
          aria-hidden="true"
        >
          <slot name="trigger-icon" :open="isOpen">
            {{ isOpen ? "◀" : "▶" }}
          </slot>
        </span>
      </button>

      <slot name="actions" />
    </div>

    <slot name="footer" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    drawerId?: string;
    storageKey?: string;
    expandTitle?: string;
    collapseTitle?: string;
    initialOpen?: boolean | null;
  }>(),
  {
    drawerId: "hero-controls-drawer",
    storageKey: "oko:hero-controls-open:v1",
    expandTitle: "Показать панель действий",
    collapseTitle: "Скрыть панель действий",
    initialOpen: null,
  },
);

const emit = defineEmits<{
  "open-change": [value: boolean];
}>();

const isOpen = ref(false);

function getLocalStorageSafe() {
  try {
    return window.localStorage || null;
  } catch {
    return null;
  }
}

onMounted(() => {
  const storage = getLocalStorageSafe();
  const raw = storage?.getItem(props.storageKey);

  if (raw === "1" || raw === "0") {
    isOpen.value = raw === "1";
    return;
  }

  if (typeof props.initialOpen === "boolean") {
    isOpen.value = props.initialOpen;
  }
});

watch(
  () => props.initialOpen,
  (value) => {
    if (typeof value !== "boolean") return;
    isOpen.value = value;
  },
);

watch(
  () => isOpen.value,
  (value) => {
    const storage = getLocalStorageSafe();
    storage?.setItem(props.storageKey, value ? "1" : "0");
    emit("open-change", value);
  },
);
</script>
