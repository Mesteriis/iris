<template>
  <!-- Корневой каркас страницы -->
  <main
    :id="layoutId"
    class="app-shell blank-page"
    :class="{
      'sidebar-hidden': !hasSidebar || sidebarHidden,
      'no-header': !hasHeader,
    }"
    :data-layout-api-version="layoutApiVersion"
  >
    <!-- Индикатор потери соединения с SSE -->
    <div
      v-if="!sseConnected"
      class="sse-disconnect-indicator"
      role="status"
      aria-live="polite"
      aria-label="Нет соединения с сервером"
    >
      <span class="sse-disconnect-indicator__icon" aria-hidden="true">⚠</span>
      <span class="sse-disconnect-indicator__text"
        >Нет соединения с сервером</span
      >
      <span class="sse-disconnect-indicator__spinner" aria-hidden="true"></span>
    </div>

    <!-- Левый сайдбар -->
    <aside
      v-show="hasSidebar && !sidebarHidden"
      :id="layoutSidebarId"
      class="sidebar blank-sidebar"
      :class="{ 'is-hidden': !hasSidebar || sidebarHidden }"
    >
      <div
        v-if="sidebarParticlesId"
        :id="sidebarParticlesId"
        class="sidebar-particles"
        aria-hidden="true"
      ></div>

      <div class="sidebar-content">
        <!-- Логотип / бренд -->
        <section
          :id="layoutSidebarBrandId"
          class="blank-sidebar-logo"
          aria-label="Бренд"
        >
          <img
            v-if="emblemSrc"
            :src="emblemSrc"
            class="logo-emblem"
            alt=""
            aria-hidden="true"
          />
          <div class="logo-text">
            <span class="logo-name">Око</span>
            <span class="logo-slogan">{{ appSlogan }}</span>
          </div>
          <UiIconButton
            v-if="hasSidebar && !sidebarHidden"
            button-class="logo-toggle-btn"
            :title="sidebarViewToggleTitle"
            :aria-label="sidebarViewToggleTitle"
            @click="handleSidebarToggle"
          >
            <PanelLeftClose class="ui-icon" />
          </UiIconButton>
        </section>
        <section
          v-if="$slots['sidebar-links']"
          :id="layoutSidebarLinksId"
          class="blank-sidebar-links"
          aria-label="Быстрые ссылки плагинов"
        >
          <slot name="sidebar-links" />
        </section>
        <!-- Основная навигация -->
        <section :id="layoutSidebarNavId" class="blank-sidebar-main">
          <slot name="sidebar-mid" />
        </section>

        <!-- Индикаторы в нижней части сайдбара -->
        <section
          v-if="$slots['sidebar-bottom-indicators']"
          :id="layoutSidebarIndicatorsId"
          class="blank-sidebar-indicators"
        >
          <slot name="sidebar-bottom-indicators" />
        </section>
      </div>
    </aside>

    <!-- Основная область -->
    <div :id="layoutMainId" class="blank-main">
      <!-- ① Шапка: вкладки + панель управления -->
      <header
        v-if="hasHeader"
        :id="layoutHeaderId"
        class="blank-main-header hero-layout"
      >
        <UiIconButton
          v-if="showSidebarToggle"
          button-class="sidebar-toggle-btn"
          :title="sidebarViewToggleTitle"
          :aria-label="sidebarViewToggleTitle"
          @click="handleSidebarToggle"
        >
          <PanelRightOpen class="ui-icon sidebar-toggle-icon" />
        </UiIconButton>

        <UiHeroGlassTabsShell
          :id="layoutHeaderTabsId"
          class="hero-title-panel"
          :emblem-src="emblemSrc"
        >
          <slot name="header-tabs" />
        </UiHeroGlassTabsShell>

        <UiDivider orientation="vertical" class="hero-header-divider" />

        <UiHeroControlsAccordion
          v-if="$slots.drawer"
          :drawer-id="headerPanelDrawerId"
          :storage-key="resolvedHeaderPanelStorageKey"
          :initial-open="headerPanelInitiallyOpen"
          @open-change="handleHeaderPanelOpenChange"
        >
          <template #drawer>
            <slot name="drawer" />
          </template>

          <template v-if="$slots['drawer-actions']" #actions>
            <slot name="drawer-actions" />
          </template>

          <template v-if="$slots['drawer-footer']" #footer>
            <slot name="drawer-footer" />
          </template>
        </UiHeroControlsAccordion>

        <UiDropdownMenu
          class="hero-action-menu align-right"
          aria-label="Системное меню"
          :items="systemActions"
          :show-caret="false"
          trigger-class="hero-icon-btn hero-accordion-action hero-system-menu-trigger"
          item-class="hero-system-menu-item"
          @action="handleSystemAction"
        >
          <template #trigger>
            <Lock class="ui-icon hero-action-icon" />
          </template>
        </UiDropdownMenu>
      </header>

      <!-- ② Основной контент -->
      <section
        :id="layoutCanvasId"
        class="blank-canvas"
        :aria-label="contentLabel"
        :style="layoutCanvasStyle"
      >
        <!-- Слот для индикаторов (показывается только если используется) -->
        <section
          v-if="$slots.indicators"
          :id="layoutCanvasIndicatorsId"
          class="blank-canvas-indicators"
        >
          <slot name="indicators" />
        </section>

        <!-- Основной контент -->
        <div class="blank-canvas-main">
          <slot name="canvas-main" />
        </div>

        <!-- Слот для плагинов (показывается только если используется) -->
        <section
          v-if="$slots.plugins"
          :id="layoutCanvasPluginsId"
          class="blank-canvas-plugins"
        >
          <slot name="plugins" />
        </section>

        <div class="blank-canvas-bg" aria-hidden="true" />
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  type Component,
  useSlots,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { PanelLeftClose, PanelRightOpen, Lock } from "lucide-vue-next";
import UiHeroGlassTabsShell from "@/components/layout/UiHeroGlassTabsShell.vue";
import UiHeroControlsAccordion from "@/components/layout/UiHeroControlsAccordion.vue";
import UiIconButton from "@/ui/actions/UiIconButton.vue";
import UiDivider from "@/ui/surfaces/UiDivider.vue";
import UiDropdownMenu from "@/primitives/overlays/UiDropdownMenu.vue";
import { openPleiadOverlay } from "@/app/navigation/nav";
import { useDashboardStore } from "@/features/stores/dashboardStore";
import { EMBLEM_SRC } from "@/features/stores/dashboard/storeConstants";
import {
  buildRouterTree,
  type RouterTreeNode,
} from "@/features/router/utils/buildRouterTree";
import {
  connectOkoSseStream,
  type OkoSseStream,
} from "@/features/services/eventStream";

// ── Unique instance IDs ───────────────────────────────────────────────────────

let layoutCounter = 0;
const instanceId = `layout-${++layoutCounter}`;

const layoutId = instanceId;
const layoutSidebarId = `${instanceId}-sidebar`;
const layoutSidebarBrandId = `${instanceId}-sidebar-brand`;
const layoutSidebarLinksId = `${instanceId}-sidebar-links`;
const layoutSidebarNavId = `${instanceId}-sidebar-nav`;
const layoutSidebarIndicatorsId = `${instanceId}-sidebar-indicators`;
const layoutMainId = `${instanceId}-main`;
const layoutHeaderId = `${instanceId}-header`;
const layoutHeaderTabsId = `${instanceId}-header-tabs`;
const layoutCanvasId = `${instanceId}-canvas`;
const layoutCanvasIndicatorsId = `${instanceId}-canvas-indicators`;
const layoutCanvasPluginsId = `${instanceId}-canvas-plugins`;

// ── Constants ─────────────────────────────────────────────────────────────────

const APP_CONSTANTS = {
  SSE_RECONNECT_DELAY_MS: 3000,
} as const;

// ── SSE Connection ────────────────────────────────────────────────────────────

const sseConnected = ref(true);
let sseStream: OkoSseStream | null = null;

function connectSse(): void {
  sseStream?.close();
  sseStream = connectOkoSseStream({
    path: "/api/v1/events/stream",
    onEvent: () => {
      sseConnected.value = true;
    },
    onError: () => {
      sseConnected.value = false;
      window.setTimeout(connectSse, APP_CONSTANTS.SSE_RECONNECT_DELAY_MS);
    },
    onOpen: () => {
      sseConnected.value = true;
    },
    onClose: () => {
      sseConnected.value = false;
    },
  });
}

// ── Props & Emits ─────────────────────────────────────────────────────────────

const props = withDefaults(
  defineProps<{
    emblemSrc: string;
    appSlogan?: string;
    layoutMode?: "default" | "no-sidebar" | "content-only";
    sidebarHidden?: boolean;
    sidebarParticlesId?: string;
    contentLabel?: string;
    headerPanelActive?: boolean;
    headerPanelDrawerId?: string;
    headerPanelStorageKey?: string;
    headerPanelInitiallyOpen?: boolean | null;
    layoutApiVersion?: "v1";
  }>(),
  {
    appSlogan: "Your Infrastructure in Sight",
    layoutMode: "default",
    sidebarHidden: false,
    sidebarParticlesId: "",
    contentLabel: "Основной контент",
    headerPanelActive: false,
    headerPanelDrawerId: "layout-header-controls-drawer",
    headerPanelStorageKey: "",
    headerPanelInitiallyOpen: null,
    layoutApiVersion: "v1",
  },
);

const emit = defineEmits<{
  "header-panel-open-change": [value: boolean];
  logout: [];
}>();

defineSlots<{
  "sidebar-links": [];
  "sidebar-mid": [];
  "sidebar-bottom-indicators": [];
  "header-tabs": [];
  drawer: [];
  "drawer-actions": [];
  "drawer-footer": [];
  indicators: [];
  "canvas-main": [];
  plugins: [];
}>();

// ── Store & Route ─────────────────────────────────────────────────────────────

const route = useRoute();
const router = useRouter();
const dashboard = useDashboardStore();
const {
  openSettingsPanel,
  sidebarView,
  sidebarViewToggleTitle,
  toggleSidebarView,
} = dashboard;

// ── Системное меню ────────────────────────────────────────────────────────

type SystemActionId =
  | "settings"
  | "kiosk"
  | "pleiad_lock"
  | "logout"
  | "navigate";

interface SystemAction {
  id: SystemActionId | string;
  label: string;
  icon?: Component | string;
  route?: string;
  children?: SystemAction[];
  action?: () => void | Promise<void>;
  danger?: boolean;
  divider?: boolean;
}

const navigationActions = computed<SystemAction[]>(() => {
  const rawRoutes = [...(router.options.routes || [])];
  const tree = buildRouterTree(rawRoutes);
  const grouped = groupRoutesBySegment(tree);

  return grouped
    .filter((group) => group.children && group.children.length > 0)
    .map((group) => ({
      id: `nav-group-${group.id}`,
      label: group.label,
      children: group.children,
    }));
});

const systemActions = computed<SystemAction[]>(() => {
  const navItems = navigationActions.value;
  const items: SystemAction[] = [];

  if (navItems.length) {
    items.push(
      {
        id: "navigation-root",
        label: "Навигация",
        children: navItems,
      },
      { id: "divider-nav", label: "", divider: true },
    );
  }

  items.push(
    { id: "settings", label: "Настройки" },
    { id: "kiosk", label: "Режим киоска" },
    { id: "pleiad_lock", label: "Заблокировать" },
    { id: "divider-1", label: "", divider: true },
    { id: "logout", label: "Выход", danger: true },
  );

  return items;
});

function groupRoutesBySegment(tree: RouterTreeNode[]): Array<{
  id: string;
  label: string;
  children: SystemAction[];
}> {
  const groups = new Map<string, { id: string; label: string; children: SystemAction[] }>();

  for (const node of tree) {
    const segment = extractTopSegment(node.path);
    const groupId = segment || "root";
    const groupLabel = segment ? humanizeSegment(segment) : "Основное";

    if (!groups.has(groupId)) {
      groups.set(groupId, { id: groupId, label: groupLabel, children: [] });
    }

    const group = groups.get(groupId);
    if (!group) continue;

    const leaves = collectLeaves(node);
    for (const leaf of leaves) {
      if (!leaf.route) continue;
      group.children.push({
        id: `nav-${leaf.id}`,
        label: leaf.label,
        route: leaf.route,
      });
    }
  }

  return Array.from(groups.values())
    .map((group) => ({
      ...group,
      children: dedupeByRoute(group.children),
    }))
    .sort((a, b) => a.label.localeCompare(b.label, "ru"));
}

function collectLeaves(node: RouterTreeNode, prefix = ""): Array<{ id: string; label: string; route?: string }> {
  const nodeId = prefix ? `${prefix}-${node.name}` : node.name;
  const routePath = node.path.startsWith("/") ? node.path : `/${node.path}`;
  const hasChildren = Boolean(node.children && node.children.length > 0);
  const ownItem = {
    id: nodeId,
    label: node.label || readableRouteLabel(node.name),
    route: routePath,
  };

  if (!hasChildren) return [ownItem];

  const nested = (node.children || []).flatMap((child) => collectLeaves(child, nodeId));
  const includeParent = routePath !== "/";
  return includeParent ? [ownItem, ...nested] : nested;
}

function dedupeByRoute(items: SystemAction[]): SystemAction[] {
  const visited = new Set<string>();
  const result: SystemAction[] = [];

  for (const item of items) {
    const key = String(item.route || item.id);
    if (visited.has(key)) continue;
    visited.add(key);
    result.push(item);
  }

  return result;
}

function extractTopSegment(path: string): string {
  const normalized = String(path || "/").trim();
  if (!normalized || normalized === "/") return "";
  return normalized
    .replace(/^\//, "")
    .split("/")
    .find(Boolean) || "";
}

function humanizeSegment(segment: string): string {
  if (segment === "ui") return "UI";
  return segment
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function readableRouteLabel(value: string): string {
  return value
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

async function toggleKioskMode(): Promise<void> {
  if (typeof document === "undefined") return;
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else {
      await document.documentElement.requestFullscreen();
    }
  } catch {
    // ignore
  }
}

function handleSystemAction(action: SystemAction): void {
  // Обработка divider — игнорируем
  if (action.divider) return;

  // Если есть custom action — выполняем его
  if (action.action) {
    void Promise.resolve(action.action());
    return;
  }

  // Если есть route — навигируем
  if (action.route) {
    void router.push(action.route);
    return;
  }

  // Встроенные действия
  switch (action.id) {
    case "settings":
      openSettingsPanel();
      break;
    case "kiosk":
      void toggleKioskMode();
      break;
    case "pleiad_lock":
      void openPleiadOverlay("route");
      break;
    case "logout":
      emit("logout");
      break;
  }
}

// ── Layout State

const hasSidebar = computed(
  () =>
    props.layoutMode !== "no-sidebar" && props.layoutMode !== "content-only",
);
const hasHeader = computed(() => props.layoutMode !== "content-only");
const showSidebarToggle = computed(
  () => hasSidebar.value && props.sidebarHidden,
);

const resolvedHeaderPanelStorageKey = computed(() => {
  const customKey = String(props.headerPanelStorageKey || "").trim();
  if (customKey) return customKey;
  const rawPath = String(route.path || "/").trim();
  const normalizedPath =
    rawPath.length > 1 && rawPath.endsWith("/")
      ? rawPath.slice(0, -1)
      : rawPath;
  return `oko:hero-controls-open:${normalizedPath || "/"}`;
});

const layoutCanvasStyle = computed(() => {
  const src = props.emblemSrc || EMBLEM_SRC;
  return {
    "--blank-canvas-emblem-url": `url('${src}')`,
  };
});

function handleSidebarToggle(): void {
  const before = sidebarView.value;
  toggleSidebarView();
  if (sidebarView.value !== before) return;
  sidebarView.value = before === "hidden" ? "detailed" : "hidden";
}

function handleHeaderPanelOpenChange(value: boolean): void {
  emit("header-panel-open-change", value);
}

function emitDevLayoutWarning(message: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent("oko:layout-validation-warning", {
      detail: { message },
    }),
  );
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(() => {
  connectSse();
});

onBeforeUnmount(() => {
  sseStream?.close();
  sseStream = null;
});

// ── Validation (DEV only) ───────────────────────────────────────────────────

if (import.meta.env.DEV) {
  const $slots = useSlots();

  // Check for actual slot names used by consumers
  const hasSidebarSlot = Boolean(
    $slots["sidebar-links"] ||
    $slots["sidebar-mid"] ||
    $slots["app.sidebar.middle"] ||
    $slots["app.sidebar.links"]
  );
  const hasHeaderSlot = Boolean(
    $slots.default ||
    $slots["app.header.tabs"] ||
    $slots["app.header.panel.drawer"] ||
    $slots["app.header.panel.actions"]
  );

  // Warning instead of error in DEV
  if (props.layoutMode === "default") {
    if (!hasSidebarSlot && !hasHeaderSlot) {
      emitDevLayoutWarning(
        '[UiBlankLayout] layoutMode="default" requires at least one slot: ' +
          '"sidebar-mid" or header content slots. ' +
          "Either provide content in these slots or use a different layoutMode.",
      );
    }
  }

  if (props.layoutMode === "no-sidebar") {
    if (hasSidebarSlot) {
      emitDevLayoutWarning(
        '[UiBlankLayout] layoutMode="no-sidebar" does not support sidebar slots. ' +
          'Remove sidebar slots or use layoutMode="default".',
      );
    }
  }

  if (props.layoutMode === "content-only") {
    if (hasSidebarSlot) {
      emitDevLayoutWarning(
        '[UiBlankLayout] layoutMode="content-only" does not support sidebar slots. ' +
          "Remove sidebar slots or use a different layoutMode.",
      );
    }
    if (hasHeaderSlot) {
      emitDevLayoutWarning(
        '[UiBlankLayout] layoutMode="content-only" does not support header slots. ' +
          "Remove header slots or use a different layoutMode.",
      );
    }
  }
}
</script>

<style scoped>
/* ── SSE Disconnect Indicator ───────────────────────────────────────────── */

.sse-disconnect-indicator {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 16px;
  background: rgba(255, 193, 7, 0.95);
  color: rgba(10, 10, 10, 0.95);
  font-size: 0.875rem;
  font-weight: 500;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.sse-disconnect-indicator__icon {
  font-size: 1rem;
  animation: sse-icon-pulse 1.5s ease-in-out infinite;
}

.sse-disconnect-indicator__text {
  flex: 1;
  text-align: center;
}

.sse-disconnect-indicator__spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(10, 10, 10, 0.2);
  border-top-color: rgba(10, 10, 10, 0.9);
  border-radius: 50%;
  animation: sse-spin 0.8s linear infinite;
}

@keyframes sse-icon-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.6;
    transform: scale(1.1);
  }
}

@keyframes sse-spin {
  to {
    transform: rotate(360deg);
  }
}

/* ── CSS Variables ───────────────────────────────────────────────────────── */

.blank-page {
  --layout-sidebar-width: 420px;
  --logo-emblem-size: 42px;
  --logo-toggle-icon-size: 18px;
  --sidebar-toggle-icon-size: 16px;
  --blank-canvas-pad: clamp(14px, 2vw, 24px);
  --sidebar-accordion-max-height: min(42vh, 340px);
}

/* ── Корневая сетка страницы ─────────────────────────────────────────── */

.blank-page {
  grid-template-columns: var(--layout-sidebar-width) minmax(0, 1fr);
  height: calc(100vh - var(--desktop-drag-strip, 0px));
  min-height: unset;
  align-items: stretch;
  overflow: hidden;
  max-width: 100%;
}

.blank-page.sidebar-hidden {
  grid-template-columns: minmax(0, 1fr);
}

.blank-page.no-header {
  grid-template-rows: minmax(0, 1fr);
}

.blank-page.no-header .blank-main {
  grid-template-rows: minmax(0, 1fr);
}

.blank-page.no-header .blank-canvas {
  height: 100%;
}

.blank-sidebar.is-hidden {
  display: none;
}

/* ── Основная колонка ────────────────────────────────────────────────── */

.blank-main {
  position: relative;
  isolation: isolate;
  min-height: 0;
  height: 100%;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 10px;
  overflow: hidden;
}

/* ── Кнопка показа панели ───────────────────────────────────────────── */

.sidebar-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: var(--ui-radius);
  background: transparent;
  border: 1px solid transparent;
  color: rgba(200, 230, 255, 0.9);
  cursor: pointer;
  transition: all 170ms ease;
}

.sidebar-toggle-btn:hover {
  background: rgba(30, 60, 90, 0.4);
  border-color: rgba(120, 183, 218, 0.2);
}

.sidebar-toggle-btn:focus-visible {
  outline: none;
  border-color: rgba(166, 225, 255, 0.4);
  box-shadow: 0 0 0 2px rgba(103, 177, 219, 0.2);
}

.sidebar-toggle-emblem {
  width: 22px;
  height: 22px;
  object-fit: contain;
  border-radius: 4px;
}

.sidebar-toggle-icon {
  width: var(--sidebar-toggle-icon-size);
  height: var(--sidebar-toggle-icon-size);
}

/* ── ① Шапка (#layout-header) ───────────────────────────────────────── */

.blank-main-header {
  position: relative;
  z-index: var(--z-layer-header);
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: visible;
  min-width: 0;
  width: 100%;
}

.blank-main-header > :deep(.hero-title-panel) {
  flex: 1;
  height: 100%;
}

.blank-main-header .sidebar-toggle-btn {
  flex-shrink: 0;
}

.blank-main-header .hero-action-menu {
  flex-shrink: 0;
}

.blank-main-header :deep(.hero-glass-tabs-shell) {
  position: relative;
  z-index: calc(var(--z-layer-header) - 10);
  overflow: visible;
  flex: 1 1 auto;
  width: 100%;
}

.blank-main-header :deep(.hero-action-menu) {
  z-index: calc(var(--z-layer-header) + 10);
}

.blank-main-header :deep(.hero-control-panel--menu .ui-menu__list) {
  z-index: calc(var(--z-layer-header) + 10);
}

/* ── ② Контент (#layout-canvas) ─────────────────────────────────────── */

.blank-canvas {
  --blank-canvas-pad: clamp(14px, 2vw, 24px);
  position: relative;
  z-index: 1;
  height: 100%;
  border: 1px solid rgba(89, 144, 166, 0.18);
  border-radius: var(--ui-radius);
  background-color: transparent;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  padding: var(--blank-canvas-pad);
  overflow: hidden;
  display: grid;
  align-content: start;
  gap: 10px;
}

.blank-canvas::before {
  content: "";
  position: absolute;
  inset: 0;
  padding: var(--blank-canvas-pad);
  background-image: var(--blank-canvas-emblem-url);
  background-repeat: no-repeat;
  background-position: center 52%;
  background-origin: content-box;
  background-size: 50% auto;
  opacity: 0.1;
  mix-blend-mode: screen;
  pointer-events: none;
  z-index: 0;
}

.blank-canvas > *:not(.blank-canvas-bg) {
  position: relative;
  z-index: 1;
}

.blank-canvas-bg {
  position: absolute;
  inset: calc(-1 * var(--blank-canvas-pad));
  display: grid;
  place-items: center;
  pointer-events: none;
  z-index: 0;
}

/* ── Слоты для индикаторов и плагинов ───────────────────────────────── */

.blank-canvas-indicators {
  position: relative;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-bottom: 8px;
}

.blank-canvas-main {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  display: grid;
  align-content: start;
  gap: 10px;
}

.blank-canvas-plugins {
  position: relative;
  z-index: 2;
  display: grid;
  gap: 10px;
  padding-top: 10px;
  margin-top: auto;
}

.blank-canvas-top,
.blank-canvas-bottom {
  min-width: 0;
  min-height: 0;
}

/* ── Сайдбар ─────────────────────────────────────────────────────────── */

.blank-sidebar {
  min-height: 0;
}

.blank-sidebar .sidebar-content {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  min-height: 0;
  gap: 10px;
}

.blank-sidebar-logo {
  grid-row: 1;
  flex: 0 0 auto;
  min-height: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 14px;
}

.logo-emblem {
  width: var(--logo-emblem-size);
  height: var(--logo-emblem-size);
  object-fit: contain;
  border-radius: var(--ui-radius);
}

.logo-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.logo-name {
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: rgba(220, 240, 255, 0.95);
}

.logo-slogan {
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  color: rgba(160, 200, 230, 0.7);
  text-transform: uppercase;
}

.logo-toggle-btn {
  margin-inline-start: auto;
  padding: 6px;
  border-radius: var(--ui-radius);
  background: transparent;
  border: 1px solid transparent;
  color: rgba(160, 200, 230, 0.7);
  cursor: pointer;
  transition: all 170ms ease;
}

.logo-toggle-btn:hover {
  background: rgba(30, 60, 90, 0.4);
  border-color: rgba(120, 183, 218, 0.2);
  color: rgba(200, 230, 255, 0.9);
}

.logo-toggle-btn:focus-visible {
  outline: none;
  border-color: rgba(166, 225, 255, 0.4);
  box-shadow: 0 0 0 2px rgba(103, 177, 219, 0.2);
}

.logo-toggle-btn .ui-icon {
  width: var(--logo-toggle-icon-size);
  height: var(--logo-toggle-icon-size);
}

.blank-sidebar-links {
  grid-row: 2;
  min-height: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 14px;
}

.blank-sidebar-links :deep(.blank-sidebar-link-btn) {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  border: 1px solid rgba(120, 183, 218, 0.24);
  background: linear-gradient(
    150deg,
    rgba(16, 37, 57, 0.62),
    rgba(10, 26, 42, 0.44)
  );
  color: rgba(188, 225, 247, 0.92);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  cursor: pointer;
  transition:
    border-color 170ms ease,
    background 170ms ease,
    color 170ms ease,
    transform 170ms ease;
}

.blank-sidebar-links :deep(.blank-sidebar-link-btn:hover) {
  border-color: rgba(162, 216, 246, 0.38);
  background: linear-gradient(
    150deg,
    rgba(20, 49, 73, 0.7),
    rgba(14, 35, 55, 0.56)
  );
  color: rgba(221, 241, 255, 0.97);
  transform: translateY(-1px);
}

.blank-sidebar-links :deep(.blank-sidebar-link-btn:focus-visible) {
  outline: none;
  border-color: rgba(166, 225, 255, 0.44);
  box-shadow: 0 0 0 2px rgba(103, 177, 219, 0.24);
}

.blank-sidebar-links :deep(.blank-sidebar-link-btn .ui-icon) {
  width: 16px;
  height: 16px;
}

.blank-sidebar-main {
  grid-row: 3;
  min-height: 0;
  overflow: hidden;
}

.blank-sidebar-indicators {
  grid-row: 4;
  flex: 0 0 auto;
  min-height: 0;
  display: grid;
  gap: 8px;
  padding: 10px;
  border-radius: var(--ui-radius);
  background: linear-gradient(
    146deg,
    rgba(15, 34, 51, 0.4),
    rgba(10, 24, 40, 0.3)
  );
  border: 1px solid rgba(120, 183, 218, 0.18);
}
</style>
