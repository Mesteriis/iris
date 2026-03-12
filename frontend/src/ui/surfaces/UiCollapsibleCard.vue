<template>
  <article class="ui-collapsible-card" :class="{ 'is-open': isOpen }">
    <header
      class="ui-collapsible-card__header panel"
      :class="{
        'is-static': !canToggle,
        'no-toggle': !props.showToggle,
        'bg-image': useImageBackground,
        'bg-icon': useIconBackground,
      }"
      :data-bg-icon="resolvedBackgroundIcon"
      :style="headerStyle"
      @click="toggleFromHeader"
    >
      <button
        v-if="props.showToggle"
        type="button"
        class="ui-collapsible-card__toggle"
        :aria-expanded="isOpen"
        :aria-controls="contentId"
        :aria-label="toggleLabel"
        :title="toggleLabel"
        :disabled="!canToggle"
        @click.stop="toggle"
      >
        <slot name="toggle" :open="isOpen">
          <span aria-hidden="true">{{ isOpen ? "-" : "+" }}</span>
        </slot>
      </button>

      <div class="ui-collapsible-card__header-content">
        <slot name="header">
          <h3 v-if="title">{{ title }}</h3>
          <p v-if="subtitle">{{ subtitle }}</p>
        </slot>
      </div>
    </header>

    <Transition
      name="ui-collapsible-card-expand"
      @before-enter="beforeEnter"
      @enter="enter"
      @after-enter="afterEnter"
      @before-leave="beforeLeave"
      @leave="leave"
      @after-leave="afterLeave"
    >
      <section
        v-if="shouldRenderContent"
        :id="contentId"
        class="ui-collapsible-card__content panel"
      >
        <div v-if="hasBodyContent" class="ui-collapsible-card__body">
          <slot name="body">
            <slot />
          </slot>
        </div>

        <footer v-if="hasFooterContent" class="ui-collapsible-card__footer">
          <slot name="footer" />
        </footer>
      </section>
    </Transition>
  </article>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, useSlots, watch } from "vue";

type AccordionListener = () => void;

const accordionGroups = new Map<string, Map<symbol, AccordionListener>>();
let cardCounter = 0;

function normalizeAccordionGroup(value: string): string {
  return String(value || "").trim();
}

function subscribeAccordionGroup(
  group: string,
  cardId: symbol,
  listener: AccordionListener,
): () => void {
  let subscribers = accordionGroups.get(group);
  if (!subscribers) {
    subscribers = new Map();
    accordionGroups.set(group, subscribers);
  }

  subscribers.set(cardId, listener);

  return () => {
    const currentSubscribers = accordionGroups.get(group);
    if (!currentSubscribers) return;
    currentSubscribers.delete(cardId);
    if (currentSubscribers.size === 0) {
      accordionGroups.delete(group);
    }
  };
}

function notifyAccordionGroup(group: string, sourceCardId: symbol): void {
  const subscribers = accordionGroups.get(group);
  if (!subscribers) return;

  for (const [cardId, listener] of subscribers.entries()) {
    if (cardId === sourceCardId) continue;
    listener();
  }
}

const props = withDefaults(
  defineProps<{
    title?: string;
    subtitle?: string;
    emblemSrc?: string;
    backgroundMode?: "auto" | "image" | "icon";
    backgroundImageSrc?: string;
    backgroundIcon?: string;
    showToggle?: boolean;
    collapsible?: boolean;
    modelValue?: boolean;
    defaultOpen?: boolean;
    accordion?: boolean;
    accordionGroup?: string;
    expandLabel?: string;
    collapseLabel?: string;
  }>(),
  {
    title: "",
    subtitle: "",
    emblemSrc: "/static/img/emblem-mark.png",
    backgroundMode: "auto",
    backgroundImageSrc: "",
    backgroundIcon: "",
    showToggle: true,
    collapsible: true,
    modelValue: undefined,
    defaultOpen: false,
    accordion: false,
    accordionGroup: "",
    expandLabel: "Expand card",
    collapseLabel: "Collapse card",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  toggle: [value: boolean];
}>();

const slots = useSlots();
const instanceIndex = ++cardCounter;
const cardId = Symbol(`ui-collapsible-card-${instanceIndex}`);
const contentId = `ui-collapsible-card-content-${instanceIndex}`;
const localOpen = ref(Boolean(props.defaultOpen));

const isControlled = computed(() => props.modelValue !== undefined);
const hasBodyContent = computed(() => Boolean(slots.body || slots.default));
const hasFooterContent = computed(() => Boolean(slots.footer));
const hasExpandableContent = computed(
  () => hasBodyContent.value || hasFooterContent.value,
);
const canToggle = computed(
  () => props.collapsible && hasExpandableContent.value,
);

const isOpen = computed(() => {
  if (!props.collapsible) return true;
  return isControlled.value ? Boolean(props.modelValue) : localOpen.value;
});

const activeAccordionGroup = computed(() => {
  if (!props.accordion) return "";
  return normalizeAccordionGroup(props.accordionGroup);
});

const shouldRenderContent = computed(() => {
  if (!hasExpandableContent.value) return false;
  if (!props.collapsible) return true;
  return isOpen.value;
});

const toggleLabel = computed(() =>
  isOpen.value ? props.collapseLabel : props.expandLabel,
);
const normalizedBackgroundMode = computed(() => {
  const raw = String(props.backgroundMode || "auto")
    .trim()
    .toLowerCase();
  if (raw === "image" || raw === "icon") return raw;
  return "auto";
});
const resolvedBackgroundIcon = computed(() => String(props.backgroundIcon || "").trim());
const resolvedBackgroundImageSrc = computed(() => {
  const imageSrc = String(props.backgroundImageSrc || "").trim();
  if (imageSrc) return imageSrc;
  return String(props.emblemSrc || "").trim();
});
const useIconBackground = computed(() => {
  const mode = normalizedBackgroundMode.value;
  if (mode === "image") return false;
  if (mode === "icon") return Boolean(resolvedBackgroundIcon.value);
  return Boolean(resolvedBackgroundIcon.value);
});
const useImageBackground = computed(() => {
  const mode = normalizedBackgroundMode.value;
  if (mode === "icon") return false;
  if (!resolvedBackgroundImageSrc.value) return false;
  if (mode === "image") return true;
  return !useIconBackground.value;
});
const headerStyle = computed<Record<string, string>>(() => {
  if (!useImageBackground.value) {
    return {
      "--ui-collapsible-card-bg-image": "none",
    };
  }
  const safeSrc = resolvedBackgroundImageSrc.value.replace(/"/g, '\\"');
  return {
    "--ui-collapsible-card-bg-image": `url("${safeSrc}")`,
  };
});

const COLLAPSE_DURATION_MS = 160;
const COLLAPSE_EASING = "cubic-bezier(0.22, 1, 0.36, 1)";

function setOpen(nextValue: boolean): void {
  if (!props.collapsible) return;
  if (!hasExpandableContent.value) return;

  const currentValue = isOpen.value;
  if (nextValue === currentValue) return;

  if (isControlled.value) {
    emit("update:modelValue", nextValue);
  } else {
    localOpen.value = nextValue;
  }
  emit("toggle", nextValue);
}

function toggle(): void {
  if (!canToggle.value) return;
  setOpen(!isOpen.value);
}

function toggleFromHeader(event: MouseEvent): void {
  if (!canToggle.value) return;
  const target = event.target;
  if (
    target instanceof Element &&
    target.closest(
      "button, a, input, textarea, select, label, [role='button'], [data-ui-no-toggle]",
    )
  ) {
    return;
  }
  toggle();
}

function closeByAccordionSignal(): void {
  if (!isOpen.value) return;
  setOpen(false);
}

let unsubscribeAccordion = () => {};

watch(
  () => activeAccordionGroup.value,
  (group) => {
    unsubscribeAccordion();
    unsubscribeAccordion = () => {};
    if (!group) return;
    unsubscribeAccordion = subscribeAccordionGroup(
      group,
      cardId,
      closeByAccordionSignal,
    );
  },
  { immediate: true },
);

watch(
  () => isOpen.value,
  (isCurrentlyOpen, wasOpen) => {
    if (!isCurrentlyOpen || isCurrentlyOpen === wasOpen) return;
    const group = activeAccordionGroup.value;
    if (!group) return;
    notifyAccordionGroup(group, cardId);
  },
);

onBeforeUnmount(() => {
  unsubscribeAccordion();
});

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function clearTransitionStyles(element: HTMLElement): void {
  element.style.transition = "";
  element.style.height = "";
  element.style.opacity = "";
  element.style.overflow = "";
  element.style.willChange = "";
}

function waitForHeightTransition(element: HTMLElement, done: () => void): void {
  let finished = false;

  const finish = () => {
    if (finished) return;
    finished = true;
    element.removeEventListener("transitionend", onTransitionEnd);
    done();
  };

  const onTransitionEnd = (event: TransitionEvent) => {
    if (event.target !== element || event.propertyName !== "height") return;
    finish();
  };

  element.addEventListener("transitionend", onTransitionEnd);
  window.setTimeout(finish, COLLAPSE_DURATION_MS + 80);
}

function beforeEnter(el: Element): void {
  if (prefersReducedMotion()) return;
  const element = el as HTMLElement;
  element.style.height = "0px";
  element.style.opacity = "0";
  element.style.overflow = "hidden";
  element.style.willChange = "height, opacity";
}

function enter(el: Element, done: () => void): void {
  const element = el as HTMLElement;
  if (prefersReducedMotion()) {
    done();
    return;
  }

  const targetHeight = `${element.scrollHeight}px`;
  element.style.transition = [
    `height ${COLLAPSE_DURATION_MS}ms ${COLLAPSE_EASING}`,
    `opacity ${Math.round(COLLAPSE_DURATION_MS * 0.9)}ms ease-out`,
  ].join(", ");
  requestAnimationFrame(() => {
    element.style.height = targetHeight;
    element.style.opacity = "1";
  });
  waitForHeightTransition(element, done);
}

function afterEnter(el: Element): void {
  clearTransitionStyles(el as HTMLElement);
}

function beforeLeave(el: Element): void {
  if (prefersReducedMotion()) return;
  const element = el as HTMLElement;
  element.style.height = `${element.scrollHeight}px`;
  element.style.opacity = "1";
  element.style.overflow = "hidden";
  element.style.willChange = "height, opacity";
}

function leave(el: Element, done: () => void): void {
  const element = el as HTMLElement;
  if (prefersReducedMotion()) {
    done();
    return;
  }

  void element.offsetHeight;
  element.style.transition = [
    `height ${COLLAPSE_DURATION_MS}ms ${COLLAPSE_EASING}`,
    `opacity ${Math.round(COLLAPSE_DURATION_MS * 0.75)}ms ease-in`,
  ].join(", ");
  requestAnimationFrame(() => {
    element.style.height = "0px";
    element.style.opacity = "0";
  });
  waitForHeightTransition(element, done);
}

function afterLeave(el: Element): void {
  clearTransitionStyles(el as HTMLElement);
}
</script>

<style scoped>
.ui-collapsible-card {
  display: grid;
  gap: 0;
}

.ui-collapsible-card__header {
  position: relative;
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-height: 62px;
  padding: 10px clamp(12px, 1.8vw, 14px);
  overflow: hidden;
  cursor: pointer;
  background:
    radial-gradient(circle at 84% 50%, rgb(116 212 188 / 8%), transparent 34%),
    radial-gradient(circle at 8% 14%, rgb(116 212 188 / 5%), transparent 26%),
    var(--ui-collapsible-card-header-bg, linear-gradient(162deg, var(--surface-strong), var(--surface)));
}

.ui-collapsible-card__header.bg-image {
  background:
    radial-gradient(circle at 84% 50%, rgb(116 212 188 / 8%), transparent 34%),
    radial-gradient(circle at 8% 14%, rgb(116 212 188 / 5%), transparent 26%),
    var(--ui-collapsible-card-bg-image, none) no-repeat
      right clamp(-26px, -1.2vw, -10px) center / clamp(108px, 20vw, 160px)
      132%,
    var(--ui-collapsible-card-header-bg, linear-gradient(162deg, var(--surface-strong), var(--surface)));
}

.ui-collapsible-card__header.no-toggle {
  grid-template-columns: minmax(0, 1fr);
}

.ui-collapsible-card__header.bg-icon::after {
  content: attr(data-bg-icon);
  position: absolute;
  right: clamp(8px, 1.4vw, 14px);
  top: 50%;
  transform: translateY(-50%);
  font-size: clamp(58px, 9vw, 98px);
  line-height: 1;
  font-weight: 700;
  color: rgb(116 212 188 / 14%);
  text-shadow: 0 0 12px rgb(34 174 142 / 18%);
  pointer-events: none;
  user-select: none;
}

.ui-collapsible-card__header.is-static {
  cursor: default;
}

.ui-collapsible-card__toggle {
  inline-size: 36px;
  block-size: 36px;
  border: 0;
  border-radius: var(--ui-radius);
  display: inline-grid;
  place-items: center;
  font: inherit;
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
}

.ui-collapsible-card__toggle:disabled {
  cursor: default;
  opacity: 0.56;
}

.ui-collapsible-card__header-content {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.ui-collapsible-card__header-content h3,
.ui-collapsible-card__header-content p {
  margin: 0;
}

.ui-collapsible-card__content {
  min-width: 0;
  display: grid;
  gap: 10px;
  padding: 12px;
  overflow: hidden;
}

.ui-collapsible-card__body,
.ui-collapsible-card__footer {
  min-width: 0;
}

.ui-collapsible-card__footer {
  display: grid;
  gap: 8px;
}

.ui-collapsible-card-expand-enter-active,
.ui-collapsible-card-expand-leave-active {
  overflow: hidden;
}

@media (prefers-reduced-motion: reduce) {
  .ui-collapsible-card-expand-enter-active,
  .ui-collapsible-card-expand-leave-active {
    transition: none;
  }
}
</style>
