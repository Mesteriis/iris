<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import {
  irisApi,
  type ControlPlaneAccessMode,
  type ControlPlaneDraft,
  type ControlPlaneDraftDiffItem,
  type ControlPlaneEdge,
  type ControlPlaneGraph,
  type ControlPlaneHeaders,
  type ControlPlaneNode,
  type ControlPlaneObservabilityOverview,
  type ControlPlaneRouteScope,
  type ControlPlaneRouteStatus,
} from "../services/api";
import { formatDateTime, formatDurationSeconds } from "../utils/format";

const loading = ref(true);
const mutating = ref(false);
const errorMessage = ref("");
const flashMessage = ref("");
const graph = ref<ControlPlaneGraph | null>(null);
const drafts = ref<ControlPlaneDraft[]>([]);
const draftDiff = ref<ControlPlaneDraftDiffItem[]>([]);
const observability = ref<ControlPlaneObservabilityOverview | null>(null);
const activeDraftId = ref<number | null>(null);
const selectedEventKey = ref<string | null>(null);
const selectedConsumerKey = ref<string | null>(null);
const selectedRouteKey = ref<string | null>(null);

const controlForm = reactive({
  actor: "ui-operator",
  accessMode: "control" as ControlPlaneAccessMode,
  reason: "topology edit",
  token: "",
});

const draftForm = reactive({
  name: "Topology draft",
  description: "Canvas-staged control plane change.",
  accessMode: "control" as ControlPlaneAccessMode,
});

const routeComposer = reactive({
  status: "active" as ControlPlaneRouteStatus,
  scopeType: "global" as ControlPlaneRouteScope,
  scopeValue: "",
  environment: "*",
  priority: 100,
  notes: "",
  shadowEnabled: false,
  shadowObserveOnly: true,
  sampleRate: 1,
  throttleLimit: "",
  throttleWindowSeconds: 60,
});

const updateComposer = reactive({
  status: "active" as ControlPlaneRouteStatus,
  scopeType: "global" as ControlPlaneRouteScope,
  scopeValue: "",
  environment: "*",
  priority: 100,
  notes: "",
  shadowEnabled: false,
  shadowObserveOnly: true,
  sampleRate: 1,
  throttleLimit: "",
  throttleWindowSeconds: 60,
});

const statusComposer = reactive({
  status: "active" as ControlPlaneRouteStatus,
  notes: "",
});

const eventNodes = computed(() =>
  (graph.value?.nodes ?? []).filter((node): node is ControlPlaneNode => node.node_type === "event"),
);
const consumerNodes = computed(() =>
  (graph.value?.nodes ?? []).filter((node): node is ControlPlaneNode => node.node_type === "consumer"),
);
const liveEdges = computed(() => graph.value?.edges ?? []);
const activeDraft = computed(() => drafts.value.find((draft) => draft.id === activeDraftId.value) ?? null);
const selectedRoute = computed(() => liveEdges.value.find((route) => route.route_key === selectedRouteKey.value) ?? null);
const selectedRouteMetrics = computed(
  () => observability.value?.routes.find((route) => route.route_key === selectedRouteKey.value) ?? null,
);
const selectedConsumerMetrics = computed(() =>
  observability.value?.consumers.find((consumer) => consumer.consumer_key === selectedConsumerKey.value) ?? null,
);

function controlHeaders(): ControlPlaneHeaders {
  return {
    actor: controlForm.actor.trim() || "ui-operator",
    accessMode: controlForm.accessMode,
    reason: controlForm.reason.trim() || undefined,
    token: controlForm.token.trim() || undefined,
  };
}

function routeTone(status: ControlPlaneRouteStatus): string {
  if (status === "active") {
    return "bullish";
  }
  if (status === "shadow" || status === "throttled") {
    return "sideways";
  }
  return "bearish";
}

function buildRouteKey(eventType: string, consumerKey: string): string {
  const scopeValue = routeComposer.scopeType === "global" ? "*" : routeComposer.scopeValue.trim() || "*";
  const environment = routeComposer.environment.trim() || "*";
  return `${eventType}:${consumerKey}:${routeComposer.scopeType}:${scopeValue}:${environment}`;
}

function syncUpdateComposer(route: ControlPlaneEdge) {
  updateComposer.status = route.status;
  updateComposer.scopeType = route.scope_type;
  updateComposer.scopeValue = route.scope_value ?? "";
  updateComposer.environment = route.environment;
  updateComposer.priority = route.priority;
  updateComposer.notes = route.notes ?? "";
  updateComposer.shadowEnabled = route.shadow.enabled;
  updateComposer.shadowObserveOnly = route.shadow.observe_only;
  updateComposer.sampleRate = route.shadow.sample_rate;
  updateComposer.throttleLimit = route.throttle.limit === null ? "" : String(route.throttle.limit);
  updateComposer.throttleWindowSeconds = route.throttle.window_seconds;
}

function buildDraftRoutePayload(
  eventKey: string,
  consumerKey: string,
  source: typeof routeComposer | typeof updateComposer,
) {
  return {
    event_type: eventKey,
    consumer_key: consumerKey,
    status: source.status,
    scope_type: source.scopeType,
    scope_value: source.scopeType === "global" ? null : source.scopeValue.trim() || null,
    environment: source.environment.trim() || "*",
    notes: source.notes.trim() || null,
    priority: source.priority,
    shadow: source.shadowEnabled
      ? {
          enabled: true,
          sample_rate: source.sampleRate,
          observe_only: source.shadowObserveOnly,
        }
      : {},
    throttle: source.throttleLimit.trim()
      ? {
          limit: Number(source.throttleLimit),
          window_seconds: source.throttleWindowSeconds,
        }
      : {},
  };
}

function selectRoute(routeKey: string) {
  selectedRouteKey.value = routeKey;
  const route = liveEdges.value.find((item) => item.route_key === routeKey);
  if (!route) {
    return;
  }
  selectedEventKey.value = route.source.replace("event:", "");
  selectedConsumerKey.value = route.target.replace("consumer:", "");
  statusComposer.status = route.status;
  statusComposer.notes = route.notes ?? "";
  syncUpdateComposer(route);
}

function selectEvent(eventKey: string) {
  selectedEventKey.value = eventKey;
}

function selectConsumer(consumerKey: string) {
  selectedConsumerKey.value = consumerKey;
}

function selectedConsumerSupportsEvent(consumerKey: string, eventKey: string): boolean {
  return graph.value?.compatibility[eventKey]?.includes(consumerKey) ?? false;
}

async function loadDraftDiff() {
  if (!activeDraftId.value) {
    draftDiff.value = [];
    return;
  }
  if (activeDraft.value?.status !== "draft") {
    draftDiff.value = [];
    return;
  }
  try {
    draftDiff.value = await irisApi.getControlPlaneDraftDiff(activeDraftId.value);
  } catch (error) {
    draftDiff.value = [];
    errorMessage.value = error instanceof Error ? error.message : "Failed to load draft diff.";
  }
}

async function loadControlPlane() {
  loading.value = true;
  errorMessage.value = "";
  try {
    const [nextGraph, nextDrafts, nextObservability] = await Promise.all([
      irisApi.getControlPlaneGraph(),
      irisApi.listControlPlaneDrafts(),
      irisApi.getControlPlaneObservability(),
    ]);
    graph.value = nextGraph;
    drafts.value = nextDrafts;
    observability.value = nextObservability;
    if (activeDraftId.value === null || !nextDrafts.some((draft) => draft.id === activeDraftId.value)) {
      activeDraftId.value = nextDrafts.find((draft) => draft.status === "draft")?.id ?? null;
    }
    await loadDraftDiff();
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Failed to load control plane.";
    errorMessage.value = detail;
  } finally {
    loading.value = false;
  }
}

async function ensureActiveDraft(): Promise<number> {
  if (activeDraft.value?.status === "draft") {
    return activeDraft.value.id;
  }

  const created = await irisApi.createControlPlaneDraft(
    {
      name: `${draftForm.name} ${new Date().toISOString().slice(11, 19)}`,
      description: draftForm.description,
      access_mode: draftForm.accessMode,
    },
    controlHeaders(),
  );
  drafts.value = [created, ...drafts.value];
  activeDraftId.value = created.id;
  await loadDraftDiff();
  return created.id;
}

async function createDraft() {
  mutating.value = true;
  flashMessage.value = "";
  errorMessage.value = "";
  try {
    await ensureActiveDraft();
    flashMessage.value = "Draft created.";
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Failed to create draft.";
  } finally {
    mutating.value = false;
  }
}

async function stageRouteCreation(eventKey: string, consumerKey: string) {
  if (!selectedConsumerSupportsEvent(consumerKey, eventKey)) {
    errorMessage.value = `Consumer '${consumerKey}' is not compatible with event '${eventKey}'.`;
    return;
  }

  const routeKey = buildRouteKey(eventKey, consumerKey);
  if (
    liveEdges.value.some((edge) => edge.route_key === routeKey) ||
    draftDiff.value.some((item) => item.route_key === routeKey && item.change_type !== "route_deleted")
  ) {
    errorMessage.value = `Route '${routeKey}' already exists in the live topology.`;
    return;
  }

  mutating.value = true;
  flashMessage.value = "";
  errorMessage.value = "";
  try {
    const draftId = await ensureActiveDraft();
    await irisApi.createControlPlaneDraftChange(
      draftId,
      {
        change_type: "route_created",
        payload: buildDraftRoutePayload(eventKey, consumerKey, routeComposer),
      },
      controlHeaders(),
    );
    await loadDraftDiff();
    flashMessage.value = `Staged route ${routeKey} in draft ${draftId}.`;
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Failed to stage route creation.";
  } finally {
    mutating.value = false;
  }
}

async function stageSelectedRoute() {
  if (!selectedEventKey.value || !selectedConsumerKey.value) {
    errorMessage.value = "Select an event and consumer before staging a route.";
    return;
  }
  await stageRouteCreation(selectedEventKey.value, selectedConsumerKey.value);
}

async function stageStatusChange() {
  if (!selectedRoute.value) {
    errorMessage.value = "Select a live route before staging a status change.";
    return;
  }

  mutating.value = true;
  flashMessage.value = "";
  errorMessage.value = "";
  try {
    const draftId = await ensureActiveDraft();
    await irisApi.createControlPlaneDraftChange(
      draftId,
      {
        change_type: "route_status_changed",
        target_route_key: selectedRoute.value.route_key,
        payload: {
          status: statusComposer.status,
          notes: statusComposer.notes.trim() || null,
        },
      },
      controlHeaders(),
    );
    await loadDraftDiff();
    flashMessage.value = `Staged ${statusComposer.status} for ${selectedRoute.value.route_key}.`;
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Failed to stage route status.";
  } finally {
    mutating.value = false;
  }
}

async function stageRouteUpdate() {
  if (!selectedRoute.value) {
    errorMessage.value = "Select a live route before staging a route update.";
    return;
  }

  const eventKey = selectedRoute.value.source.replace("event:", "");
  const consumerKey = selectedRoute.value.target.replace("consumer:", "");

  mutating.value = true;
  flashMessage.value = "";
  errorMessage.value = "";
  try {
    const draftId = await ensureActiveDraft();
    await irisApi.createControlPlaneDraftChange(
      draftId,
      {
        change_type: "route_updated",
        target_route_key: selectedRoute.value.route_key,
        payload: buildDraftRoutePayload(eventKey, consumerKey, updateComposer),
      },
      controlHeaders(),
    );
    await loadDraftDiff();
    flashMessage.value = `Staged route update for ${selectedRoute.value.route_key}.`;
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Failed to stage route update.";
  } finally {
    mutating.value = false;
  }
}

async function stageRouteDelete() {
  if (!selectedRoute.value) {
    errorMessage.value = "Select a live route before staging route deletion.";
    return;
  }

  mutating.value = true;
  flashMessage.value = "";
  errorMessage.value = "";
  try {
    const draftId = await ensureActiveDraft();
    await irisApi.createControlPlaneDraftChange(
      draftId,
      {
        change_type: "route_deleted",
        target_route_key: selectedRoute.value.route_key,
        payload: {},
      },
      controlHeaders(),
    );
    await loadDraftDiff();
    flashMessage.value = `Staged route deletion for ${selectedRoute.value.route_key}.`;
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Failed to stage route deletion.";
  } finally {
    mutating.value = false;
  }
}

async function applyActiveDraft() {
  if (!activeDraftId.value) {
    errorMessage.value = "Create or select a draft before applying.";
    return;
  }

  mutating.value = true;
  flashMessage.value = "";
  errorMessage.value = "";
  try {
    const result = await irisApi.applyControlPlaneDraft(activeDraftId.value, controlHeaders());
    flashMessage.value = `Draft applied as topology version ${result.published_version_number}.`;
    activeDraftId.value = null;
    await loadControlPlane();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Failed to apply draft.";
  } finally {
    mutating.value = false;
  }
}

async function discardActiveDraft() {
  if (!activeDraftId.value) {
    errorMessage.value = "Select a draft before discarding.";
    return;
  }

  mutating.value = true;
  flashMessage.value = "";
  errorMessage.value = "";
  try {
    await irisApi.discardControlPlaneDraft(activeDraftId.value, controlHeaders());
    flashMessage.value = `Draft ${activeDraftId.value} discarded.`;
    activeDraftId.value = null;
    await loadControlPlane();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Failed to discard draft.";
  } finally {
    mutating.value = false;
  }
}

function handleDraftSelection(event: Event) {
  const target = event.target as HTMLSelectElement;
  activeDraftId.value = target.value ? Number(target.value) : null;
  void loadDraftDiff();
}

function handleEventDragStart(eventKey: string, dragEvent: DragEvent) {
  dragEvent.dataTransfer?.setData("text/plain", eventKey);
}

async function handleConsumerDrop(consumerKey: string, dragEvent: DragEvent) {
  dragEvent.preventDefault();
  const eventKey = dragEvent.dataTransfer?.getData("text/plain");
  if (!eventKey) {
    return;
  }
  selectedEventKey.value = eventKey;
  selectedConsumerKey.value = consumerKey;
  await stageRouteCreation(eventKey, consumerKey);
}

function diffDescriptor(item: ControlPlaneDraftDiffItem): string {
  if (item.change_type === "route_created") {
    return "create";
  }
  if (item.change_type === "route_updated") {
    return "update";
  }
  if (item.change_type === "route_deleted") {
    return "delete";
  }
  return "status";
}

onMounted(() => {
  void loadControlPlane();
});
</script>

<template>
  <section class="dashboard-grid topology-page">
    <div class="hero-panel topology-hero">
      <div class="hero-panel__copy">
        <p class="hero-panel__eyebrow">Event control plane</p>
        <h2>Route domain events through a draftable topology instead of hardcoded worker wiring.</h2>
        <p>
          Drag an event onto a compatible consumer to stage a declarative route rule. Drafts stay
          out of the live runtime until you apply them.
        </p>
      </div>

      <div class="hero-panel__stats">
        <article class="mini-stat">
          <span>Published version</span>
          <strong>{{ graph?.version_number ?? "NA" }}</strong>
          <small>{{ formatDateTime(graph?.created_at ?? null) }}</small>
        </article>
        <article class="mini-stat">
          <span>Live routes</span>
          <strong>{{ liveEdges.length }}</strong>
          <small>{{ observability?.muted_route_count ?? 0 }} muted</small>
        </article>
        <article class="mini-stat">
          <span>Shadow routes</span>
          <strong>{{ observability?.shadow_route_count ?? 0 }}</strong>
          <small>{{ observability?.dead_consumer_count ?? 0 }} dead consumers</small>
        </article>
        <article class="mini-stat">
          <span>Throughput</span>
          <strong>{{ observability?.throughput ?? 0 }}</strong>
          <small>{{ observability?.failure_count ?? 0 }} failures tracked</small>
        </article>
      </div>
    </div>

    <section class="surface-card topology-toolbar">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Control context</p>
          <h3>Observe vs control</h3>
        </div>
        <button class="action-chip" type="button" :disabled="loading || mutating" @click="loadControlPlane()">
          Refresh topology
        </button>
      </div>

      <div class="topology-toolbar__grid">
        <label>
          <span>Actor</span>
          <input v-model="controlForm.actor" type="text" placeholder="ui-operator" />
        </label>
        <label>
          <span>Mode</span>
          <select v-model="controlForm.accessMode">
            <option value="observe">observe</option>
            <option value="control">control</option>
          </select>
        </label>
        <label>
          <span>Reason</span>
          <input v-model="controlForm.reason" type="text" placeholder="topology edit" />
        </label>
        <label>
          <span>Control token</span>
          <input v-model="controlForm.token" type="password" placeholder="optional" />
        </label>
      </div>

      <div v-if="flashMessage" class="topology-flash topology-flash--success">{{ flashMessage }}</div>
      <div v-if="errorMessage" class="topology-flash topology-flash--error">{{ errorMessage }}</div>
    </section>

    <section class="detail-grid__row topology-grid">
      <article class="surface-card topology-surface">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Draft flow</p>
            <h3>Stage first, publish later</h3>
          </div>
          <p>{{ drafts.filter((draft) => draft.status === "draft").length }} open drafts</p>
        </div>

        <div class="topology-draft-bar">
          <label>
            <span>Active draft</span>
            <select :value="activeDraftId ?? ''" @change="handleDraftSelection">
              <option value="">none</option>
              <option v-for="draft in drafts" :key="draft.id" :value="draft.id">
                #{{ draft.id }} {{ draft.name }} / {{ draft.status }}
              </option>
            </select>
          </label>
          <label>
            <span>Draft name</span>
            <input v-model="draftForm.name" type="text" placeholder="Topology draft" />
          </label>
          <label>
            <span>Description</span>
            <input v-model="draftForm.description" type="text" placeholder="Canvas-staged change" />
          </label>
          <button class="action-chip" type="button" :disabled="mutating" @click="createDraft()">Create draft</button>
          <button class="action-chip" type="button" :disabled="!activeDraftId || mutating" @click="applyActiveDraft()">
            Apply draft
          </button>
          <button class="action-chip action-chip--danger" type="button" :disabled="!activeDraftId || mutating" @click="discardActiveDraft()">
            Discard draft
          </button>
        </div>

        <div class="topology-workbench">
          <section class="topology-column">
            <div class="panel-heading">
              <span>Events</span>
              <span>{{ eventNodes.length }}</span>
            </div>
            <button
              v-for="node in eventNodes"
              :key="node.id"
              class="topology-node topology-node--event"
              :class="{ 'is-selected': selectedEventKey === node.key }"
              draggable="true"
              @click="selectEvent(node.key)"
              @dragstart="handleEventDragStart(node.key, $event)"
            >
              <strong>{{ node.key }}</strong>
              <small>{{ node.domain }}</small>
            </button>
          </section>

          <section class="topology-column topology-column--center">
            <div class="panel-heading">
              <span>Live routes</span>
              <span>{{ liveEdges.length }}</span>
            </div>

            <div v-if="loading" class="surface-state">Loading topology graph...</div>
            <div v-else class="topology-routes">
              <button
                v-for="edge in liveEdges"
                :key="edge.route_key"
                class="topology-route"
                :class="{ 'is-selected': selectedRouteKey === edge.route_key }"
                type="button"
                @click="selectRoute(edge.route_key)"
              >
                <div>
                  <strong>{{ edge.route_key }}</strong>
                  <p>{{ edge.source.replace('event:', '') }} -> {{ edge.target.replace('consumer:', '') }}</p>
                </div>
                <div class="topology-route__meta">
                  <span class="trend-badge" :class="`trend-badge--${routeTone(edge.status)}`">{{ edge.status }}</span>
                  <small>{{ edge.scope_type }} / {{ edge.environment }}</small>
                </div>
              </button>
            </div>

            <div class="topology-diff">
              <div class="panel-heading">
                <span>Draft diff</span>
                <span>{{ draftDiff.length }}</span>
              </div>
              <div v-if="draftDiff.length === 0" class="surface-state">
                Drop an event onto a consumer or stage a route status change to populate the draft.
              </div>
              <button
                v-for="item in draftDiff"
                :key="`${item.change_type}-${item.route_key}`"
                class="topology-diff__item"
                type="button"
                @click="selectedRouteKey = item.route_key"
              >
                <strong>{{ item.route_key }}</strong>
                <small>{{ diffDescriptor(item) }}</small>
              </button>
            </div>
          </section>

          <section class="topology-column">
            <div class="panel-heading">
              <span>Consumers</span>
              <span>{{ consumerNodes.length }}</span>
            </div>
            <button
              v-for="node in consumerNodes"
              :key="node.id"
              class="topology-node topology-node--consumer"
              :class="{
                'is-selected': selectedConsumerKey === node.key,
                'is-incompatible': selectedEventKey && !selectedConsumerSupportsEvent(node.key, selectedEventKey),
              }"
              type="button"
              @click="selectConsumer(node.key)"
              @dragover.prevent
              @drop="handleConsumerDrop(node.key, $event)"
            >
              <strong>{{ node.key }}</strong>
              <small>{{ node.domain }}</small>
              <span class="topology-node__hint">
                {{
                  selectedEventKey
                    ? (selectedConsumerSupportsEvent(node.key, selectedEventKey) ? "drop to stage" : "incompatible")
                    : "pick or drop"
                }}
              </span>
            </button>
          </section>
        </div>

        <div class="topology-composer">
          <div class="panel-heading">
            <span>Route composer</span>
            <span>{{ selectedEventKey ?? "event" }} -> {{ selectedConsumerKey ?? "consumer" }}</span>
          </div>

          <div class="topology-composer__grid">
            <label>
              <span>Status</span>
              <select v-model="routeComposer.status">
                <option value="active">active</option>
                <option value="muted">muted</option>
                <option value="paused">paused</option>
                <option value="throttled">throttled</option>
                <option value="shadow">shadow</option>
                <option value="disabled">disabled</option>
              </select>
            </label>
            <label>
              <span>Scope</span>
              <select v-model="routeComposer.scopeType">
                <option value="global">global</option>
                <option value="domain">domain</option>
                <option value="symbol">symbol</option>
                <option value="exchange">exchange</option>
                <option value="timeframe">timeframe</option>
                <option value="environment">environment</option>
              </select>
            </label>
            <label>
              <span>Scope value</span>
              <input v-model="routeComposer.scopeValue" type="text" placeholder="BTCUSD / 60 / prod" />
            </label>
            <label>
              <span>Environment</span>
              <input v-model="routeComposer.environment" type="text" placeholder="*" />
            </label>
            <label>
              <span>Priority</span>
              <input v-model.number="routeComposer.priority" type="number" min="1" step="1" />
            </label>
            <label>
              <span>Throttle limit</span>
              <input v-model="routeComposer.throttleLimit" type="number" min="1" placeholder="optional" />
            </label>
            <label>
              <span>Throttle window</span>
              <input v-model.number="routeComposer.throttleWindowSeconds" type="number" min="1" step="1" />
            </label>
            <label>
              <span>Sample rate</span>
              <input v-model.number="routeComposer.sampleRate" type="number" min="0" max="1" step="0.1" />
            </label>
            <label class="topology-toggle">
              <input v-model="routeComposer.shadowEnabled" type="checkbox" />
              <span>Shadow delivery</span>
            </label>
            <label class="topology-toggle">
              <input v-model="routeComposer.shadowObserveOnly" type="checkbox" />
              <span>Observe only</span>
            </label>
            <label class="topology-composer__notes">
              <span>Notes</span>
              <input v-model="routeComposer.notes" type="text" placeholder="Declarative route notes" />
            </label>
          </div>

          <button class="action-chip" type="button" :disabled="mutating" @click="stageSelectedRoute()">
            Stage route in draft
          </button>
        </div>
      </article>

      <aside class="surface-card topology-inspector">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Inspector</p>
            <h3>Selected route or consumer</h3>
          </div>
          <p>{{ selectedRouteKey ?? selectedConsumerKey ?? "Nothing selected" }}</p>
        </div>

        <div v-if="selectedRoute" class="topology-inspector__block">
          <div class="panel-heading">
            <span>Live route</span>
            <span class="trend-badge" :class="`trend-badge--${routeTone(selectedRoute.status)}`">{{ selectedRoute.status }}</span>
          </div>
          <dl class="system-grid">
            <div>
              <dt>Event</dt>
              <dd>{{ selectedRoute.source.replace("event:", "") }}</dd>
            </div>
            <div>
              <dt>Consumer</dt>
              <dd>{{ selectedRoute.target.replace("consumer:", "") }}</dd>
            </div>
            <div>
              <dt>Scope</dt>
              <dd>{{ selectedRoute.scope_type }} / {{ selectedRoute.scope_value ?? "*" }}</dd>
            </div>
            <div>
              <dt>Environment</dt>
              <dd>{{ selectedRoute.environment }}</dd>
            </div>
            <div>
              <dt>Priority</dt>
              <dd>{{ selectedRoute.priority }}</dd>
            </div>
            <div>
              <dt>Notes</dt>
              <dd>{{ selectedRoute.notes ?? "none" }}</dd>
            </div>
          </dl>

          <div class="topology-inspector__metrics">
            <div class="indicator-card">
              <span>Throughput</span>
              <strong>{{ selectedRouteMetrics?.throughput ?? 0 }}</strong>
            </div>
            <div class="indicator-card">
              <span>Latency</span>
              <strong>{{ selectedRouteMetrics?.avg_latency_ms ?? "NA" }}</strong>
            </div>
            <div class="indicator-card">
              <span>Lag</span>
              <strong>{{ formatDurationSeconds(selectedRouteMetrics?.lag_seconds ?? null) }}</strong>
            </div>
          </div>

          <div class="topology-inspector__status">
            <label>
              <span>Stage status</span>
              <select v-model="statusComposer.status">
                <option value="active">active</option>
                <option value="muted">muted</option>
                <option value="paused">paused</option>
                <option value="throttled">throttled</option>
                <option value="shadow">shadow</option>
                <option value="disabled">disabled</option>
              </select>
            </label>
            <label>
              <span>Status notes</span>
              <input v-model="statusComposer.notes" type="text" placeholder="Stage a note with the status change" />
            </label>
            <button class="action-chip" type="button" :disabled="mutating" @click="stageStatusChange()">
              Stage status change
            </button>
          </div>

          <div class="topology-inspector__status">
            <label>
              <span>Route status</span>
              <select v-model="updateComposer.status">
                <option value="active">active</option>
                <option value="muted">muted</option>
                <option value="paused">paused</option>
                <option value="throttled">throttled</option>
                <option value="shadow">shadow</option>
                <option value="disabled">disabled</option>
              </select>
            </label>
            <label>
              <span>Scope</span>
              <select v-model="updateComposer.scopeType">
                <option value="global">global</option>
                <option value="domain">domain</option>
                <option value="symbol">symbol</option>
                <option value="exchange">exchange</option>
                <option value="timeframe">timeframe</option>
                <option value="environment">environment</option>
              </select>
            </label>
            <label>
              <span>Scope value</span>
              <input v-model="updateComposer.scopeValue" type="text" placeholder="BTCUSD / 60 / prod" />
            </label>
            <label>
              <span>Environment</span>
              <input v-model="updateComposer.environment" type="text" placeholder="*" />
            </label>
            <label>
              <span>Priority</span>
              <input v-model.number="updateComposer.priority" type="number" min="1" step="1" />
            </label>
            <label>
              <span>Throttle limit</span>
              <input v-model="updateComposer.throttleLimit" type="number" min="1" placeholder="optional" />
            </label>
            <label>
              <span>Throttle window</span>
              <input v-model.number="updateComposer.throttleWindowSeconds" type="number" min="1" step="1" />
            </label>
            <label>
              <span>Sample rate</span>
              <input v-model.number="updateComposer.sampleRate" type="number" min="0" max="1" step="0.1" />
            </label>
            <label class="topology-toggle">
              <input v-model="updateComposer.shadowEnabled" type="checkbox" />
              <span>Shadow delivery</span>
            </label>
            <label class="topology-toggle">
              <input v-model="updateComposer.shadowObserveOnly" type="checkbox" />
              <span>Observe only</span>
            </label>
            <label class="topology-composer__notes">
              <span>Route notes</span>
              <input v-model="updateComposer.notes" type="text" placeholder="Update declarative route notes" />
            </label>
            <div class="topology-inspector__actions">
              <button class="action-chip" type="button" :disabled="mutating" @click="stageRouteUpdate()">
                Stage route update
              </button>
              <button class="action-chip action-chip--danger" type="button" :disabled="mutating" @click="stageRouteDelete()">
                Stage route delete
              </button>
            </div>
          </div>
        </div>

        <div v-else-if="selectedConsumerMetrics" class="topology-inspector__block">
          <div class="panel-heading">
            <span>Consumer observability</span>
            <span :class="`status-pill status-pill--${selectedConsumerMetrics.dead ? 'down' : 'ok'}`">
              {{ selectedConsumerMetrics.dead ? "Dead" : "Live" }}
            </span>
          </div>
          <dl class="system-grid">
            <div>
              <dt>Processed</dt>
              <dd>{{ selectedConsumerMetrics.processed_total }}</dd>
            </div>
            <div>
              <dt>Failures</dt>
              <dd>{{ selectedConsumerMetrics.failure_count }}</dd>
            </div>
            <div>
              <dt>Last seen</dt>
              <dd>{{ formatDateTime(selectedConsumerMetrics.last_seen_at) }}</dd>
            </div>
            <div>
              <dt>Lag</dt>
              <dd>{{ formatDurationSeconds(selectedConsumerMetrics.lag_seconds ?? null) }}</dd>
            </div>
          </dl>
        </div>

        <div v-else class="surface-state">
          Select a route card or consumer node to inspect live routing metadata and observability.
        </div>
      </aside>
    </section>
  </section>
</template>
