<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

import AssetTypeIcon from "../components/assets/AssetTypeIcon.vue";
import { useCoinStore } from "../stores/coinStore";
import UiBaseModal from "../ui/overlays/UiBaseModal.vue";
import { formatCurrency, formatCurrencyDelta, formatDateTime, formatSignalType } from "../utils/format";

type AssetKind = "all" | "commodity" | "crypto" | "energy" | "equity" | "forex" | "index" | "metal" | "generic";
const PRIMARY_NAME_MAX_LENGTH = 8;

const coinStore = useCoinStore();
const filters = reactive({
  query: "",
  assetType: "all",
});
const addCoinForm = reactive({
  symbol: "",
  name: "",
  asset_type: "",
  source: "",
  enabled: true,
});
const isCreateModalOpen = ref(false);
const updatedSymbols = ref<Record<string, boolean>>({});
const initialized = ref(false);
let previousRowSignatures = new Map<string, string>();
const updateTimers = new Map<string, number>();

const signalTypesBySymbol = computed(() => {
  const map = new Map<string, string[]>();
  for (const [symbol, signals] of coinStore.signalsBySymbol.entries()) {
    map.set(
      symbol,
      [...new Set(signals.map((signal) => signal.signal_type))].map((signalType) => formatSignalType(signalType)),
    );
  }
  return map;
});

const assetRows = computed(() =>
  [...coinStore.coins]
    .map((coin) => {
      const symbol = coin.symbol.toUpperCase();
      const metric = coinStore.metricsBySymbol.get(symbol);
      const signalCount = coinStore.signalsBySymbol.get(symbol)?.length ?? 0;
      const signalTypes = signalTypesBySymbol.value.get(symbol) ?? [];

      return {
        ...coin,
        ...metric,
        signalCount,
        signalTypes,
        typeKind: assetTypeKind(coin.asset_type),
      };
    })
    .sort((left, right) => left.sort_order - right.sort_order || left.symbol.localeCompare(right.symbol)),
);

const assetTabs = computed(() => {
  const counts = new Map<string, number>();
  for (const row of assetRows.value) {
    const key = row.asset_type || "untyped";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  return [
    {
      key: "all",
      label: "All assets",
      count: assetRows.value.length,
      kind: "all" as AssetKind,
    },
    ...[...counts.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, count]) => ({
        key,
        label: key,
        count,
        kind: assetTypeKind(key),
      })),
  ];
});

const filteredRows = computed(() => {
  const query = filters.query.trim().toLowerCase();

  return assetRows.value.filter((row) => {
    const tabMatch = filters.assetType === "all" || (row.asset_type || "untyped") === filters.assetType;
    const queryMatch =
      query.length === 0 ||
      row.symbol.toLowerCase().includes(query) ||
      row.name.toLowerCase().includes(query) ||
      (row.asset_type || "").toLowerCase().includes(query);

    return tabMatch && queryMatch;
  });
});

function buildRowSignature(row: (typeof assetRows.value)[number]): string {
  return JSON.stringify({
    price_current: row.price_current ?? null,
    price_change_1h: row.price_change_1h ?? null,
    updated_at: row.updated_at ?? null,
    last_history_sync_at: row.last_history_sync_at ?? null,
    signal_count: row.signalCount,
    signal_types: row.signalTypes,
  });
}

function markRowUpdated(symbol: string) {
  const currentTimer = updateTimers.get(symbol);
  if (currentTimer !== undefined) {
    window.clearTimeout(currentTimer);
  }

  updatedSymbols.value = {
    ...updatedSymbols.value,
    [symbol]: true,
  };

  const nextTimer = window.setTimeout(() => {
    const nextState = { ...updatedSymbols.value };
    delete nextState[symbol];
    updatedSymbols.value = nextState;
    updateTimers.delete(symbol);
  }, 900);

  updateTimers.set(symbol, nextTimer);
}

function assetTone(change: number | null | undefined): "positive" | "negative" | "neutral" {
  if (change === null || change === undefined || Number.isNaN(change)) {
    return "neutral";
  }
  if (change > 0) {
    return "positive";
  }
  if (change < 0) {
    return "negative";
  }
  return "neutral";
}

function assetToneLabel(change: number | null | undefined): string {
  if (change === null || change === undefined || Number.isNaN(change)) {
    return "—";
  }
  return "1h";
}

function assetTypeKind(assetType: string | null | undefined): AssetKind {
  const normalized = assetType?.trim().toLowerCase() ?? "";

  if (normalized.includes("crypto")) {
    return "crypto";
  }
  if (normalized.includes("forex") || normalized === "fx") {
    return "forex";
  }
  if (normalized.includes("equity") || normalized.includes("stock")) {
    return "equity";
  }
  if (normalized.includes("energy")) {
    return "energy";
  }
  if (normalized.includes("metal")) {
    return "metal";
  }
  if (normalized.includes("commodity")) {
    return "commodity";
  }
  if (normalized.includes("index") || normalized.includes("etf")) {
    return "index";
  }
  return "generic";
}

function assetUpdateLabel(row: (typeof assetRows.value)[number]): string {
  return `Updated ${formatDateTime(row.updated_at ?? row.last_history_sync_at ?? null)}`;
}

function assetPrimaryLabel(row: (typeof assetRows.value)[number]): string {
  const normalizedName = row.name.trim();
  if (normalizedName.length > 0 && normalizedName.length <= PRIMARY_NAME_MAX_LENGTH) {
    return normalizedName;
  }
  return row.symbol;
}

function assetSecondaryLabel(row: (typeof assetRows.value)[number]): string {
  const primary = assetPrimaryLabel(row);
  if (primary === row.symbol) {
    return row.name;
  }
  return row.symbol;
}

function handleCardPointerMove(event: MouseEvent) {
  const card = event.currentTarget as HTMLElement | null;
  if (!card) {
    return;
  }

  const bounds = card.getBoundingClientRect();
  const pointerX = (event.clientX - bounds.left) / bounds.width;
  const pointerY = (event.clientY - bounds.top) / bounds.height;
  const tiltY = (pointerX - 0.5) * 10;
  const tiltX = (0.5 - pointerY) * 10;
  const shiftX = (pointerX - 0.5) * 10;
  const shiftY = (pointerY - 0.5) * 10;

  card.style.setProperty("--asset-tilt-x", `${tiltX.toFixed(2)}deg`);
  card.style.setProperty("--asset-tilt-y", `${tiltY.toFixed(2)}deg`);
  card.style.setProperty("--asset-shift-x", `${shiftX.toFixed(2)}px`);
  card.style.setProperty("--asset-shift-y", `${shiftY.toFixed(2)}px`);
  card.style.setProperty("--asset-glow-x", `${(pointerX * 100).toFixed(2)}%`);
  card.style.setProperty("--asset-glow-y", `${(pointerY * 100).toFixed(2)}%`);
}

function handleCardPointerLeave(event: MouseEvent) {
  const card = event.currentTarget as HTMLElement | null;
  if (!card) {
    return;
  }

  card.style.setProperty("--asset-tilt-x", "0deg");
  card.style.setProperty("--asset-tilt-y", "0deg");
  card.style.setProperty("--asset-shift-x", "0px");
  card.style.setProperty("--asset-shift-y", "0px");
  card.style.setProperty("--asset-glow-x", "50%");
  card.style.setProperty("--asset-glow-y", "50%");
}

function selectAssetTab(tabKey: string) {
  filters.assetType = tabKey;
}

function resetCreateCoinForm() {
  addCoinForm.symbol = "";
  addCoinForm.name = "";
  addCoinForm.asset_type = "";
  addCoinForm.source = "";
  addCoinForm.enabled = true;
}

function openCreateCoinModal() {
  coinStore.createCoinError = "";
  coinStore.createCoinSuccess = "";
  isCreateModalOpen.value = true;
}

function closeCreateCoinModal() {
  if (coinStore.isCreatingCoin) {
    return;
  }
  isCreateModalOpen.value = false;
}

async function submitCoinForm() {
  const created = await coinStore.createCoin({
    symbol: addCoinForm.symbol.trim(),
    name: addCoinForm.name.trim(),
    asset_type: addCoinForm.asset_type.trim() || undefined,
    source: addCoinForm.source.trim() || undefined,
    enabled: addCoinForm.enabled,
  });

  if (!created) {
    return;
  }

  resetCreateCoinForm();
  closeCreateCoinModal();
}

watch(
  assetRows,
  (rows) => {
    const nextSignatures = new Map(rows.map((row) => [row.symbol, buildRowSignature(row)]));

    if (initialized.value) {
      for (const row of rows) {
        const previous = previousRowSignatures.get(row.symbol);
        const next = nextSignatures.get(row.symbol);
        if (previous && next && previous !== next) {
          markRowUpdated(row.symbol);
        }
      }
    } else {
      initialized.value = true;
    }

    previousRowSignatures = nextSignatures;
  },
  { immediate: true },
);

onMounted(() => {
  void coinStore.bootstrapDashboard();
});

onBeforeUnmount(() => {
  for (const timer of updateTimers.values()) {
    window.clearTimeout(timer);
  }
  updateTimers.clear();
});
</script>

<template>
  <section class="dashboard-grid assets-page">
    <section class="surface-card assets-toolbar-shell">
      <div class="assets-toolbar-shell__title">
        <h1>Asset</h1>
      </div>

      <div class="assets-toolbar-shell__controls">
        <label class="assets-search" aria-label="Search assets">
          <svg class="assets-search__icon" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="7.1" cy="7.1" r="3.9" />
            <path d="m10.2 10.2 2.8 2.8" />
          </svg>
          <input v-model.trim="filters.query" type="text" placeholder="Search" />
        </label>

        <div class="assets-filter-strip" role="tablist" aria-label="Asset types">
          <button
            v-for="tab in assetTabs"
            :key="tab.key"
            class="assets-filter-button"
            :class="{ 'is-active': filters.assetType === tab.key }"
            :aria-label="tab.label"
            :title="`${tab.label} · ${tab.count}`"
            type="button"
            @click="selectAssetTab(tab.key)"
          >
            <AssetTypeIcon :kind="tab.kind" />
          </button>
        </div>

        <button
          class="assets-icon-button"
          aria-label="Add asset"
          title="Add asset"
          type="button"
          @click="openCreateCoinModal"
        >
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M8 3.1v9.8" />
            <path d="M3.1 8h9.8" />
          </svg>
        </button>
      </div>
    </section>

    <section class="surface-card assets-stage">
      <div v-if="coinStore.isBootstrapping" class="surface-state">Loading assets...</div>
      <div v-else-if="filteredRows.length === 0" class="surface-state">No assets returned for the current filter.</div>
      <div v-else class="asset-card-grid">
        <article
          v-for="row in filteredRows"
          :key="row.symbol"
          class="asset-card"
          :class="[
            `asset-card--${assetTone(row.price_change_1h)}`,
            { 'asset-card--updated': updatedSymbols[row.symbol] },
          ]"
          @mousemove="handleCardPointerMove"
          @mouseleave="handleCardPointerLeave"
        >
          <div class="asset-card__body">
            <div class="asset-card__header">
              <RouterLink class="asset-title-link" :title="assetSecondaryLabel(row)" :to="`/assets/${row.symbol}`">
                <strong>{{ assetPrimaryLabel(row) }}</strong>
              </RouterLink>
              <span class="soft-badge asset-window-badge" :class="`soft-badge--${assetTone(row.price_change_1h)}`">
                {{ assetToneLabel(row.price_change_1h) }}
              </span>
            </div>

            <div class="asset-card__quote">
              <strong>{{ formatCurrency(row.price_current ?? null) }}</strong>
            </div>

            <div class="asset-card__footer">
              <div class="asset-card__delta">
                <small :class="{ positive: (row.price_change_1h ?? 0) > 0, negative: (row.price_change_1h ?? 0) < 0 }">
                  {{ formatCurrencyDelta(row.price_change_1h) }}
                </small>
                <span class="asset-card__delta-label">1h</span>
              </div>

              <div class="asset-card__meta-cluster">
                <span class="asset-mini-badge asset-mini-badge--ghost" :title="assetUpdateLabel(row)">
                  <svg class="asset-mini-badge__icon" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <circle cx="8" cy="8" r="4.75" />
                    <path d="M8 5.2v3.1l2 1.4" />
                  </svg>
                </span>

                <span class="asset-mini-badge" :class="`asset-mini-badge--${row.typeKind}`" :title="row.asset_type || 'No type'">
                  <AssetTypeIcon :kind="row.typeKind" />
                </span>

                <details v-if="row.signalTypes.length > 0" class="asset-signal-popover asset-signal-popover--mini">
                  <summary class="asset-mini-badge asset-mini-badge--accent" :title="`${row.signalCount} signals`">
                    <svg class="asset-mini-badge__icon" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                      <path d="M2.4 10.3h2.2L6 7.2l2.1 5 1.8-3.8h3.7" />
                    </svg>
                    <span>{{ row.signalCount }}</span>
                  </summary>
                  <div class="asset-signal-popover__menu">
                    <strong>Signals</strong>
                    <ul>
                      <li v-for="signalType in row.signalTypes" :key="`${row.symbol}-${signalType}`">
                        {{ signalType }}
                      </li>
                    </ul>
                  </div>
                </details>
                <span v-else class="asset-mini-badge asset-mini-badge--muted" title="No signals">
                  <svg class="asset-mini-badge__icon" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path d="M2.4 10.3h2.2L6 7.2l2.1 5 1.8-3.8h3.7" />
                  </svg>
                  <span>0</span>
                </span>
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>

    <UiBaseModal
      :open="isCreateModalOpen"
      backdropClass="ui-modal-backdrop"
      modalClass="ui-modal-panel assets-modal-panel"
      @backdrop="closeCreateCoinModal"
    >
      <section class="assets-modal">
        <div class="assets-modal__header">
          <div>
            <p class="section-head__eyebrow">Add asset</p>
            <h2>New coin</h2>
          </div>
          <button
            class="assets-icon-button assets-icon-button--ghost"
            aria-label="Close add asset dialog"
            type="button"
            @click="closeCreateCoinModal"
          >
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="m4.2 4.2 7.6 7.6" />
              <path d="m11.8 4.2-7.6 7.6" />
            </svg>
          </button>
        </div>

        <form class="assets-modal__form" @submit.prevent="submitCoinForm">
          <div class="assets-modal__grid">
            <label class="field">
              <span>Symbol</span>
              <input v-model.trim="addCoinForm.symbol" placeholder="Enter symbol" required type="text" />
            </label>
            <label class="field">
              <span>Name</span>
              <input v-model.trim="addCoinForm.name" placeholder="Enter name" required type="text" />
            </label>
            <label class="field">
              <span>Type</span>
              <input v-model.trim="addCoinForm.asset_type" placeholder="Optional" type="text" />
            </label>
            <label class="field">
              <span>Source</span>
              <input v-model.trim="addCoinForm.source" placeholder="Optional" type="text" />
            </label>
          </div>

          <label class="field field--checkbox assets-modal__checkbox">
            <input v-model="addCoinForm.enabled" type="checkbox" />
            <span>Enable sync after create</span>
          </label>

          <p v-if="coinStore.createCoinError" class="form-message form-message--error">
            {{ coinStore.createCoinError }}
          </p>

          <div class="assets-modal__actions">
            <button class="action-chip action-chip--compact" type="button" @click="closeCreateCoinModal">Cancel</button>
            <button class="action-chip" :disabled="coinStore.isCreatingCoin" type="submit">
              {{ coinStore.isCreatingCoin ? "Creating..." : "Add coin" }}
            </button>
          </div>
        </form>
      </section>
    </UiBaseModal>
  </section>
</template>
