<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import { formatDateTime } from "../../utils/format";
import { useShellStore } from "../../stores/shellStore";

const route = useRoute();
const shellStore = useShellStore();
const sidebarOpen = ref(false);
let refreshTimer: number | null = null;

const navItems = [
  {
    name: "assets",
    to: "/",
    label: "Assets",
    note: "Quotes",
  },
  {
    name: "market",
    to: "/market",
    label: "Market",
    note: "Signals",
  },
  {
    name: "portfolio",
    to: "/portfolio",
    label: "Portfolio",
    note: "Exposure",
  },
  {
    name: "research",
    to: "/research",
    label: "Research",
    note: "Patterns",
  },
  {
    name: "runtime",
    to: "/runtime",
    label: "Runtime",
    note: "Jobs",
  },
  {
    name: "control-plane",
    to: "/control-plane",
    label: "Control Plane",
    note: "Routing ops",
  },
] as const;

const pageTitle = computed(() =>
  typeof route.meta.title === "string" ? route.meta.title : "IRIS operator console",
);
const pageSubtitle = computed(() =>
  typeof route.meta.description === "string" ? route.meta.description : "Operational workspace.",
);
const showShellHeader = computed(() => route.meta.hideShellHeader !== true);
const systemStatusLabel = computed(() => {
  if (shellStore.runtimeOnline) {
    return "Online";
  }
  if (shellStore.loading) {
    return "Syncing";
  }
  return "Offline";
});
const systemStatusClass = computed(() => {
  if (shellStore.runtimeOnline) {
    return "status-pill--ok";
  }
  if (shellStore.loading) {
    return "status-pill--syncing";
  }
  return "status-pill--down";
});

function isActiveRoute(name: string): boolean {
  return route.name === name;
}

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value;
}

function closeSidebar() {
  sidebarOpen.value = false;
}

onMounted(() => {
  void shellStore.bootstrap();
  refreshTimer = window.setInterval(() => {
    void shellStore.refresh();
  }, 30000);
});

onBeforeUnmount(() => {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer);
  }
});
</script>

<template>
  <div class="iris-shell" :class="{ 'sidebar-open': sidebarOpen }">
    <aside class="iris-sidebar">
      <div class="iris-sidebar__backdrop" />

      <section class="iris-brand">
        <div class="iris-brand__badge">IR</div>
        <div>
          <p class="iris-brand__title">IRIS</p>
          <p class="iris-brand__subtitle">market intelligence console</p>
        </div>
      </section>

      <nav class="iris-nav" aria-label="Primary navigation">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          :to="item.to"
          class="iris-nav__link"
          :class="{ 'is-active': isActiveRoute(item.name) }"
          @click="closeSidebar"
        >
          <span>{{ item.label }}</span>
          <small>{{ item.note }}</small>
        </RouterLink>
      </nav>

      <div class="iris-sidebar__footer">
        <section class="iris-sidebar__panel iris-sidebar__panel--compact">
          <div class="panel-heading">
            <span>Runtime</span>
            <span class="status-pill" :class="systemStatusClass">{{ systemStatusLabel }}</span>
          </div>

          <dl class="system-grid">
            <div>
              <dt>Jobs</dt>
              <dd>{{ shellStore.backgroundJobs }}</dd>
            </div>
            <div>
              <dt>Cooling</dt>
              <dd>{{ shellStore.coolingSources }}</dd>
            </div>
            <div>
              <dt>Assets</dt>
              <dd>{{ shellStore.trackedAssets }}</dd>
            </div>
            <div>
              <dt>Errors</dt>
              <dd>{{ shellStore.errorJobs }}</dd>
            </div>
          </dl>

          <p v-if="shellStore.error" class="surface-state surface-state--error">{{ shellStore.error }}</p>
          <small v-else class="iris-sidebar__meta">Updated {{ formatDateTime(shellStore.lastUpdatedAt) }}</small>
        </section>
      </div>
    </aside>

    <div class="iris-main">
      <header v-if="showShellHeader" class="iris-header iris-header--shell">
        <div>
          <button class="iris-mobile-toggle" type="button" @click="toggleSidebar">
            {{ sidebarOpen ? "Close menu" : "Open menu" }}
          </button>
          <p class="iris-header__eyebrow">Operator surface</p>
          <h1 class="iris-header__title">{{ pageTitle }}</h1>
          <p class="iris-header__subtitle">{{ pageSubtitle }}</p>
        </div>
      </header>
      <button v-else class="iris-mobile-toggle iris-mobile-toggle--standalone" type="button" @click="toggleSidebar">
        {{ sidebarOpen ? "Close menu" : "Open menu" }}
      </button>

      <section class="iris-canvas">
        <slot />
      </section>
    </div>
  </div>
</template>
