<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import {
  irisApi,
  type ControlPlaneAccessMode,
  type ControlPlaneAuditEntry,
  type ControlPlaneConsumer,
  type ControlPlaneDraft,
  type ControlPlaneDraftDiffItem,
  type ControlPlaneEventDefinition,
  type ControlPlaneGraph,
  type ControlPlaneHeaders,
  type ControlPlaneObservabilityOverview,
  type ControlPlaneRoute,
  type ControlPlaneRouteFilters,
  type ControlPlaneRouteScope,
  type ControlPlaneRouteStatus,
} from "../services/api";
import PageToolbar from "../components/layout/PageToolbar.vue";
import { formatDateTime, formatDurationSeconds } from "../utils/format";

type InspectorMode = "route" | "event" | "consumer";

interface RouteComposerState {
  status: ControlPlaneRouteStatus;
  scopeType: ControlPlaneRouteScope;
  scopeValue: string;
  environment: string;
  priority: number;
  notes: string;
  shadowEnabled: boolean;
  shadowObserveOnly: boolean;
  sampleRate: number;
  throttleLimit: string;
  throttleWindowSeconds: number;
  filterSymbols: string;
  filterTimeframes: string;
  filterExchanges: string;
  filterConfidence: string;
  metadataJson: string;
}

const AUDIT_LIMIT = 40;

function createRouteComposerState(): RouteComposerState {
  return {
    status: "active",
    scopeType: "global",
    scopeValue: "",
    environment: "*",
    priority: 100,
    notes: "",
    shadowEnabled: false,
    shadowObserveOnly: true,
    sampleRate: 1,
    throttleLimit: "",
    throttleWindowSeconds: 60,
    filterSymbols: "",
    filterTimeframes: "",
    filterExchanges: "",
    filterConfidence: "",
    metadataJson: "",
  };
}

const loading = ref(true);
const mutating = ref(false);
const errorMessage = ref("");
const flashMessage = ref("");
const graph = ref<ControlPlaneGraph | null>(null);
const eventRegistry = ref<ControlPlaneEventDefinition[]>([]);
const consumerRegistry = ref<ControlPlaneConsumer[]>([]);
const routeInventory = ref<ControlPlaneRoute[]>([]);
const drafts = ref<ControlPlaneDraft[]>([]);
const draftDiff = ref<ControlPlaneDraftDiffItem[]>([]);
const auditEntries = ref<ControlPlaneAuditEntry[]>([]);
const observability = ref<ControlPlaneObservabilityOverview | null>(null);
const activeDraftId = ref<number | null>(null);
const selectedEventKey = ref<string | null>(null);
const selectedConsumerKey = ref<string | null>(null);
const selectedRouteKey = ref<string | null>(null);
const inspectorMode = ref<InspectorMode>("event");

const controlForm = reactive({
  actor: "",
  accessMode: "control" as ControlPlaneAccessMode,
  reason: "",
  token: "",
});

const draftForm = reactive({
  name: "",
  description: "",
  accessMode: "control" as ControlPlaneAccessMode,
});

const routeComposer = reactive(createRouteComposerState());
const updateComposer = reactive(createRouteComposerState());

const statusComposer = reactive({
  status: "active" as ControlPlaneRouteStatus,
  notes: "",
});

const liveRoutes = computed(() => routeInventory.value);
const activeDraft = computed(() => drafts.value.find((draft) => draft.id === activeDraftId.value) ?? null);
const openDraftCount = computed(() => drafts.value.filter((draft) => draft.status === "draft").length);
const controlEventCount = computed(() => eventRegistry.value.filter((eventItem) => eventItem.is_control_event).length);
const systemManagedRouteCount = computed(() =>
  liveRoutes.value.filter((route) => route.system_managed).length,
);
const selectedRoute = computed(() => liveRoutes.value.find((route) => route.route_key === selectedRouteKey.value) ?? null);
const selectedDraftDiffItem = computed(
  () => draftDiff.value.find((item) => item.route_key === selectedRouteKey.value) ?? null,
);
const selectedRouteMetrics = computed(
  () => observability.value?.routes.find((route) => route.route_key === selectedRouteKey.value) ?? null,
);
const selectedConsumerMetrics = computed(
  () => observability.value?.consumers.find((consumer) => consumer.consumer_key === selectedConsumerKey.value) ?? null,
);
const selectedEventDefinition = computed(
  () => eventRegistry.value.find((eventItem) => eventItem.event_type === selectedEventKey.value) ?? null,
);
const selectedConsumerDefinition = computed(
  () => consumerRegistry.value.find((consumer) => consumer.consumer_key === selectedConsumerKey.value) ?? null,
);
const selectedEventCompatibleConsumers = computed(() => {
  if (!selectedEventKey.value) {
    return [];
  }
  return consumerRegistry.value.filter((consumer) =>
    selectedConsumerSupportsEvent(consumer.consumer_key, selectedEventKey.value!),
  );
});
const selectedEventRoutes = computed(() => {
  if (!selectedEventKey.value) {
    return [];
  }
  return liveRoutes.value.filter((route) => route.event_type === selectedEventKey.value);
});
const selectedConsumerRoutes = computed(() => {
  if (!selectedConsumerKey.value) {
    return [];
  }
  return liveRoutes.value.filter((route) => route.consumer_key === selectedConsumerKey.value);
});
const selectedEventAudit = computed(() => {
  if (!selectedEventKey.value) {
    return [];
  }
  return auditEntries.value.filter((entry) => auditEventType(entry) === selectedEventKey.value).slice(0, 6);
});
const inspectorTitle = computed(() => {
  if (inspectorMode.value === "route") {
    return "Selected route";
  }
  if (inspectorMode.value === "consumer") {
    return "Selected consumer";
  }
  return "Selected event";
});
const inspectorTarget = computed(() => {
  if (inspectorMode.value === "route") {
    return selectedRouteKey.value ?? "No route selected";
  }
  if (inspectorMode.value === "consumer") {
    return selectedConsumerKey.value ?? "No consumer selected";
  }
  return selectedEventKey.value ?? "No event selected";
});

function controlHeaders(): ControlPlaneHeaders {
  return {
    actor: controlForm.actor.trim(),
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

function parseRouteKey(routeKey: string): { eventType: string | null; consumerKey: string | null } {
  const parts = routeKey.split(":");
  return {
    eventType: parts[0] ?? null,
    consumerKey: parts[1] ?? null,
  };
}

function readRecordValue(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function listRecordValues(record: Record<string, unknown>, key: string): string[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function parseStringList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseNumberList(value: string): number[] {
  const items = parseStringList(value);
  const numbers = items.map((item) => Number(item));
  if (numbers.some((item) => !Number.isFinite(item))) {
    throw new Error("Timeframe filters must be comma-separated numbers.");
  }
  return numbers;
}

function parseOptionalNumber(value: string, label: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${label} must be numeric.`);
  }
  return parsed;
}

function parseMetadataJson(value: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) {
    return {};
  }
  const parsed = JSON.parse(trimmed) as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("Metadata filters must be a JSON object.");
  }
  return parsed as Record<string, unknown>;
}

function serializeMetadataJson(value: Record<string, unknown>): string {
  if (Object.keys(value).length === 0) {
    return "";
  }
  return JSON.stringify(value, null, 2);
}

function routingHintFields(eventItem: ControlPlaneEventDefinition): string {
  const fields = Array.isArray(eventItem.routing_hints_json.filter_fields)
    ? eventItem.routing_hints_json.filter_fields.filter((item): item is string => typeof item === "string")
    : [];
  return fields.length > 0 ? fields.join(", ") : "none";
}

function listLabel(values: readonly (string | number)[]): string {
  return values.length > 0 ? values.join(", ") : "none";
}

function routeScopeSummary(route: Pick<ControlPlaneRoute, "scope_type" | "scope_value" | "environment">): string {
  return `${route.scope_type} / ${route.scope_value ?? "*"} / ${route.environment}`;
}

function routeFiltersSummary(filters: ControlPlaneRouteFilters): string {
  const parts: string[] = [];
  if (filters.symbol.length > 0) {
    parts.push(`symbols ${filters.symbol.join(", ")}`);
  }
  if (filters.timeframe.length > 0) {
    parts.push(`timeframes ${filters.timeframe.join(", ")}`);
  }
  if (filters.exchange.length > 0) {
    parts.push(`exchanges ${filters.exchange.join(", ")}`);
  }
  if (filters.confidence !== null) {
    parts.push(`confidence >= ${filters.confidence}`);
  }
  if (Object.keys(filters.metadata).length > 0) {
    parts.push(`metadata ${Object.keys(filters.metadata).join(", ")}`);
  }
  return parts.length > 0 ? parts.join(" | ") : "all events";
}

function auditEventType(entry: ControlPlaneAuditEntry): string | null {
  return (
    readRecordValue(entry.after_json, "event_type") ??
    readRecordValue(entry.before_json, "event_type") ??
    parseRouteKey(entry.route_key_snapshot).eventType
  );
}

function auditConsumerKey(entry: ControlPlaneAuditEntry): string | null {
  return (
    readRecordValue(entry.after_json, "consumer_key") ??
    readRecordValue(entry.before_json, "consumer_key") ??
    parseRouteKey(entry.route_key_snapshot).consumerKey
  );
}

function auditHeadline(entry: ControlPlaneAuditEntry): string {
  const eventType = auditEventType(entry);
  const consumerKey = auditConsumerKey(entry);
  if (eventType && consumerKey) {
    return `${eventType} -> ${consumerKey}`;
  }
  return entry.route_key_snapshot;
}

function auditContextLabel(entry: ControlPlaneAuditEntry): string {
  const source = readRecordValue(entry.context_json, "source");
  const revision = readRecordValue(entry.context_json, "migration_revision");
  const pieces = [source, revision].filter((item): item is string => Boolean(item));
  return pieces.length > 0 ? pieces.join(" / ") : "runtime";
}

function buildRouteKey(eventType: string, consumerKey: string): string {
  const scopeValue = routeComposer.scopeType === "global" ? "*" : routeComposer.scopeValue.trim() || "*";
  const environment = routeComposer.environment.trim() || "*";
  return `${eventType}:${consumerKey}:${routeComposer.scopeType}:${scopeValue}:${environment}`;
}

function syncUpdateComposer(route: ControlPlaneRoute) {
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
  updateComposer.filterSymbols = route.filters.symbol.join(", ");
  updateComposer.filterTimeframes = route.filters.timeframe.join(", ");
  updateComposer.filterExchanges = route.filters.exchange.join(", ");
  updateComposer.filterConfidence = route.filters.confidence === null ? "" : String(route.filters.confidence);
  updateComposer.metadataJson = serializeMetadataJson(route.filters.metadata);
}

function buildRouteFilters(source: RouteComposerState): ControlPlaneRouteFilters {
  return {
    symbol: parseStringList(source.filterSymbols),
    timeframe: parseNumberList(source.filterTimeframes),
    exchange: parseStringList(source.filterExchanges),
    confidence: parseOptionalNumber(source.filterConfidence, "Confidence filter"),
    metadata: parseMetadataJson(source.metadataJson),
  };
}

function buildDraftRoutePayload(eventKey: string, consumerKey: string, source: RouteComposerState) {
  return {
    event_type: eventKey,
    consumer_key: consumerKey,
    status: source.status,
    scope_type: source.scopeType,
    scope_value: source.scopeType === "global" ? null : source.scopeValue.trim() || null,
    environment: source.environment.trim() || "*",
    filters: buildRouteFilters(source),
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

function selectedConsumerSupportsEvent(consumerKey: string, eventKey: string): boolean {
  const graphCompatibility = graph.value?.compatibility[eventKey]?.includes(consumerKey);
  if (graphCompatibility !== undefined) {
    return graphCompatibility;
  }
  return (
    consumerRegistry.value.find((consumer) => consumer.consumer_key === consumerKey)?.compatible_event_types_json.includes(eventKey) ??
    false
  );
}

function ensureCompatibleConsumerSelection(eventKey: string) {
  if (selectedConsumerKey.value && selectedConsumerSupportsEvent(selectedConsumerKey.value, eventKey)) {
    return;
  }
  selectedConsumerKey.value =
    consumerRegistry.value.find((consumer) => selectedConsumerSupportsEvent(consumer.consumer_key, eventKey))
      ?.consumer_key ?? null;
}

function selectRoute(routeKey: string) {
  inspectorMode.value = "route";
  selectedRouteKey.value = routeKey;
  const route = liveRoutes.value.find((item) => item.route_key === routeKey);
  if (!route) {
    return;
  }
  selectedEventKey.value = route.event_type;
  selectedConsumerKey.value = route.consumer_key;
  statusComposer.status = route.status;
  statusComposer.notes = route.notes ?? "";
  syncUpdateComposer(route);
}

function selectDraftDiffItem(item: ControlPlaneDraftDiffItem) {
  const liveRoute = liveRoutes.value.find((route) => route.route_key === item.route_key);
  if (liveRoute) {
    selectRoute(liveRoute.route_key);
    return;
  }
  inspectorMode.value = "route";
  selectedRouteKey.value = item.route_key;
  selectedEventKey.value =
    readRecordValue(item.after, "event_type") ??
    readRecordValue(item.before, "event_type") ??
    parseRouteKey(item.route_key).eventType;
  selectedConsumerKey.value =
    readRecordValue(item.after, "consumer_key") ??
    readRecordValue(item.before, "consumer_key") ??
    parseRouteKey(item.route_key).consumerKey;
}

function selectAuditEntry(entry: ControlPlaneAuditEntry) {
  const liveRoute = liveRoutes.value.find((route) => route.route_key === entry.route_key_snapshot);
  if (liveRoute) {
    selectRoute(liveRoute.route_key);
    return;
  }
  inspectorMode.value = "route";
  selectedRouteKey.value = entry.route_key_snapshot;
  selectedEventKey.value = auditEventType(entry);
  selectedConsumerKey.value = auditConsumerKey(entry);
}

function selectEvent(eventKey: string) {
  inspectorMode.value = "event";
  selectedRouteKey.value = null;
  selectedEventKey.value = eventKey;
  ensureCompatibleConsumerSelection(eventKey);
}

function selectConsumer(consumerKey: string) {
  inspectorMode.value = "consumer";
  selectedRouteKey.value = null;
  selectedConsumerKey.value = consumerKey;
}

async function loadDraftDiff() {
  if (!activeDraftId.value || activeDraft.value?.status !== "draft") {
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
    const [
      nextGraph,
      nextEvents,
      nextConsumers,
      nextRoutes,
      nextDrafts,
      nextAudit,
      nextObservability,
    ] = await Promise.all([
      irisApi.getControlPlaneGraph(),
      irisApi.listControlPlaneEvents(),
      irisApi.listControlPlaneConsumers(),
      irisApi.listControlPlaneRoutes(),
      irisApi.listControlPlaneDrafts(),
      irisApi.listControlPlaneAudit(AUDIT_LIMIT),
      irisApi.getControlPlaneObservability(),
    ]);

    graph.value = nextGraph;
    eventRegistry.value = [...nextEvents].sort((left, right) => left.event_type.localeCompare(right.event_type));
    consumerRegistry.value = [...nextConsumers].sort((left, right) => left.consumer_key.localeCompare(right.consumer_key));
    routeInventory.value = [...nextRoutes].sort((left, right) =>
      `${left.event_type}:${left.consumer_key}`.localeCompare(`${right.event_type}:${right.consumer_key}`),
    );
    drafts.value = [...nextDrafts].sort((left, right) => right.updated_at.localeCompare(left.updated_at));
    auditEntries.value = nextAudit;
    observability.value = nextObservability;

    if (activeDraftId.value === null || !nextDrafts.some((draft) => draft.id === activeDraftId.value)) {
      activeDraftId.value = nextDrafts.find((draft) => draft.status === "draft")?.id ?? null;
    }

    if (selectedRouteKey.value && !nextRoutes.some((route) => route.route_key === selectedRouteKey.value)) {
      selectedRouteKey.value = null;
      if (inspectorMode.value === "route") {
        inspectorMode.value = "event";
      }
    }

    if (!selectedEventKey.value || !nextEvents.some((eventItem) => eventItem.event_type === selectedEventKey.value)) {
      selectedEventKey.value = nextEvents[0]?.event_type ?? null;
    }

    if (
      selectedConsumerKey.value &&
      !nextConsumers.some((consumer) => consumer.consumer_key === selectedConsumerKey.value)
    ) {
      selectedConsumerKey.value = null;
    }

    if (selectedEventKey.value) {
      ensureCompatibleConsumerSelection(selectedEventKey.value);
    }

    if (selectedRouteKey.value) {
      const route = nextRoutes.find((item) => item.route_key === selectedRouteKey.value);
      if (route) {
        statusComposer.status = route.status;
        statusComposer.notes = route.notes ?? "";
        syncUpdateComposer(route);
      }
    }

    await loadDraftDiff();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Failed to load control plane.";
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
      name: `${draftForm.name.trim() || "Draft"} ${new Date().toISOString().slice(11, 19)}`,
      description: draftForm.description.trim() || undefined,
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
    liveRoutes.value.some((route) => route.route_key === routeKey) ||
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
        payload: buildDraftRoutePayload(selectedRoute.value.event_type, selectedRoute.value.consumer_key, updateComposer),
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
  inspectorMode.value = "route";
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
    <PageToolbar title="Control Plane">
      <template #controls>
        <button class="action-chip action-chip--compact" type="button" :disabled="loading || mutating" @click="loadControlPlane()">
          Refresh
        </button>
      </template>

      <template #stats>
        <article class="page-toolbar__stat">
          <span>Published</span>
          <strong>{{ graph?.version_number ?? "—" }}</strong>
          <small>{{ formatDateTime(graph?.created_at ?? null) }}</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Registry</span>
          <strong>{{ eventRegistry.length }} / {{ consumerRegistry.length }}</strong>
          <small>{{ controlEventCount }} control events</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Routes</span>
          <strong>{{ liveRoutes.length }}</strong>
          <small>{{ systemManagedRouteCount }} system managed</small>
        </article>
        <article class="page-toolbar__stat">
          <span>Throughput</span>
          <strong>{{ observability?.throughput ?? 0 }}</strong>
          <small>{{ observability?.failure_count ?? 0 }} failures tracked</small>
        </article>
      </template>
    </PageToolbar>

    <section class="surface-card topology-toolbar">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Control context</p>
          <h3>Observe vs control</h3>
        </div>
        <small>{{ drafts.length }} drafts / {{ liveRoutes.length }} routes</small>
      </div>

      <div class="topology-toolbar__grid">
        <label>
          <span>Actor</span>
          <input v-model="controlForm.actor" type="text" placeholder="Enter actor" />
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
          <input v-model="controlForm.reason" type="text" placeholder="Enter reason" />
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
            <p class="section-head__eyebrow">Registry and routing</p>
            <h3>Events, consumers, and live route inventory</h3>
          </div>
          <p>{{ liveRoutes.length }} live routes / {{ openDraftCount }} open drafts</p>
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
            <input v-model="draftForm.name" type="text" placeholder="Enter draft name" />
          </label>
          <label>
            <span>Description</span>
            <input v-model="draftForm.description" type="text" placeholder="Enter draft description" />
          </label>
          <button class="action-chip" type="button" :disabled="mutating" @click="createDraft()">Create draft</button>
          <button class="action-chip" type="button" :disabled="!activeDraftId || mutating" @click="applyActiveDraft()">
            Apply draft
          </button>
          <button
            class="action-chip action-chip--danger"
            type="button"
            :disabled="!activeDraftId || mutating"
            @click="discardActiveDraft()"
          >
            Discard draft
          </button>
        </div>

        <div class="topology-workbench">
          <section class="topology-column">
            <div class="panel-heading">
              <span>Event registry</span>
              <span>{{ eventRegistry.length }}</span>
            </div>

            <div v-if="loading" class="surface-state">Loading event registry...</div>
            <div v-else class="topology-list">
              <button
                v-for="eventItem in eventRegistry"
                :key="eventItem.id"
                class="topology-node topology-node--event"
                :class="{ 'is-selected': selectedEventKey === eventItem.event_type && inspectorMode === 'event' }"
                draggable="true"
                type="button"
                @click="selectEvent(eventItem.event_type)"
                @dragstart="handleEventDragStart(eventItem.event_type, $event)"
              >
                <strong>{{ eventItem.display_name }}</strong>
                <small>{{ eventItem.event_type }}</small>
                <span class="topology-node__hint">
                  {{ eventItem.domain }} · {{ eventItem.is_control_event ? "control" : "runtime" }}
                </span>
              </button>
            </div>
          </section>

          <section class="topology-column topology-column--center">
            <div class="panel-heading">
              <span>Route inventory</span>
              <span>{{ liveRoutes.length }}</span>
            </div>

            <div v-if="loading" class="surface-state">Loading live routes...</div>
            <div v-else class="topology-routes">
              <button
                v-for="route in liveRoutes"
                :key="route.route_key"
                class="topology-route"
                :class="{ 'is-selected': selectedRouteKey === route.route_key }"
                type="button"
                @click="selectRoute(route.route_key)"
              >
                <div class="topology-route__copy">
                  <strong>{{ route.event_type }} -> {{ route.consumer_key }}</strong>
                  <small>{{ route.route_key }}</small>
                  <small>{{ routeScopeSummary(route) }}</small>
                </div>
                <div class="topology-route__meta">
                  <span class="trend-badge" :class="`trend-badge--${routeTone(route.status)}`">{{ route.status }}</span>
                  <small>{{ route.system_managed ? "system" : "user" }} managed</small>
                </div>
              </button>
            </div>

            <div class="topology-diff">
              <div class="panel-heading">
                <span>Draft diff</span>
                <span>{{ draftDiff.length }}</span>
              </div>
              <div v-if="draftDiff.length === 0" class="surface-state">
                Stage a route or update an existing rule to populate the active draft diff.
              </div>
              <button
                v-for="item in draftDiff"
                :key="`${item.change_type}-${item.route_key}`"
                class="topology-diff__item"
                type="button"
                @click="selectDraftDiffItem(item)"
              >
                <strong>{{ item.route_key }}</strong>
                <small>{{ diffDescriptor(item) }}</small>
              </button>
            </div>
          </section>

          <section class="topology-column">
            <div class="panel-heading">
              <span>Consumer registry</span>
              <span>{{ consumerRegistry.length }}</span>
            </div>

            <div v-if="loading" class="surface-state">Loading consumers...</div>
            <div v-else class="topology-list">
              <button
                v-for="consumer in consumerRegistry"
                :key="consumer.id"
                class="topology-node topology-node--consumer"
                :class="{
                  'is-selected': selectedConsumerKey === consumer.consumer_key && inspectorMode === 'consumer',
                  'is-incompatible': selectedEventKey && !selectedConsumerSupportsEvent(consumer.consumer_key, selectedEventKey),
                }"
                type="button"
                @click="selectConsumer(consumer.consumer_key)"
                @dragover.prevent
                @drop="handleConsumerDrop(consumer.consumer_key, $event)"
              >
                <strong>{{ consumer.display_name }}</strong>
                <small>{{ consumer.consumer_key }}</small>
                <span class="topology-node__hint">
                  {{
                    selectedEventKey
                      ? (selectedConsumerSupportsEvent(consumer.consumer_key, selectedEventKey)
                          ? `${consumer.domain} · drop to stage`
                          : `${consumer.domain} · incompatible`)
                      : `${consumer.domain} · ${consumer.delivery_mode}`
                  }}
                </span>
              </button>
            </div>
          </section>
        </div>

        <div class="topology-composer">
          <div class="panel-heading">
            <span>Draft composer</span>
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
              <input v-model="routeComposer.scopeValue" type="text" placeholder="Enter scope value" />
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
            <label>
              <span>Symbols</span>
              <input v-model="routeComposer.filterSymbols" type="text" placeholder="Comma-separated symbols" />
            </label>
            <label>
              <span>Timeframes</span>
              <input v-model="routeComposer.filterTimeframes" type="text" placeholder="Comma-separated timeframes" />
            </label>
            <label>
              <span>Exchanges</span>
              <input v-model="routeComposer.filterExchanges" type="text" placeholder="Comma-separated exchanges" />
            </label>
            <label>
              <span>Min confidence</span>
              <input v-model="routeComposer.filterConfidence" type="number" min="0" max="1" step="0.01" placeholder="optional" />
            </label>
            <label class="topology-toggle">
              <input v-model="routeComposer.shadowEnabled" type="checkbox" />
              <span>Shadow delivery</span>
            </label>
            <label class="topology-toggle">
              <input v-model="routeComposer.shadowObserveOnly" type="checkbox" />
              <span>Observe only</span>
            </label>
            <label class="topology-composer__textarea">
              <span>Metadata JSON</span>
              <textarea
                v-model="routeComposer.metadataJson"
                rows="3"
                placeholder="JSON object"
              />
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
            <h3>{{ inspectorTitle }}</h3>
          </div>
          <p>{{ inspectorTarget }}</p>
        </div>

        <div v-if="inspectorMode === 'route' && selectedRoute" class="topology-inspector__block">
          <div class="panel-heading">
            <span>Live route</span>
            <span class="trend-badge" :class="`trend-badge--${routeTone(selectedRoute.status)}`">{{ selectedRoute.status }}</span>
          </div>
          <dl class="system-grid">
            <div>
              <dt>Event</dt>
              <dd>{{ selectedRoute.event_type }}</dd>
            </div>
            <div>
              <dt>Consumer</dt>
              <dd>{{ selectedRoute.consumer_key }}</dd>
            </div>
            <div>
              <dt>Scope</dt>
              <dd>{{ routeScopeSummary(selectedRoute) }}</dd>
            </div>
            <div>
              <dt>Priority</dt>
              <dd>{{ selectedRoute.priority }}</dd>
            </div>
            <div>
              <dt>Filters</dt>
              <dd>{{ routeFiltersSummary(selectedRoute.filters) }}</dd>
            </div>
            <div>
              <dt>Managed</dt>
              <dd>{{ selectedRoute.system_managed ? "system" : "user" }}</dd>
            </div>
            <div>
              <dt>Notes</dt>
              <dd>{{ selectedRoute.notes ?? "none" }}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{{ formatDateTime(selectedRoute.updated_at) }}</dd>
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

          <div class="panel-heading">
            <span>Stage rule update</span>
            <span>{{ selectedRoute.route_key }}</span>
          </div>

          <div class="topology-composer__grid topology-composer__grid--compact">
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
              <input v-model="updateComposer.scopeValue" type="text" placeholder="Enter scope value" />
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
            <label>
              <span>Symbols</span>
              <input v-model="updateComposer.filterSymbols" type="text" placeholder="Comma-separated symbols" />
            </label>
            <label>
              <span>Timeframes</span>
              <input v-model="updateComposer.filterTimeframes" type="text" placeholder="Comma-separated timeframes" />
            </label>
            <label>
              <span>Exchanges</span>
              <input v-model="updateComposer.filterExchanges" type="text" placeholder="Comma-separated exchanges" />
            </label>
            <label>
              <span>Min confidence</span>
              <input v-model="updateComposer.filterConfidence" type="number" min="0" max="1" step="0.01" placeholder="optional" />
            </label>
            <label class="topology-toggle">
              <input v-model="updateComposer.shadowEnabled" type="checkbox" />
              <span>Shadow delivery</span>
            </label>
            <label class="topology-toggle">
              <input v-model="updateComposer.shadowObserveOnly" type="checkbox" />
              <span>Observe only</span>
            </label>
            <label class="topology-composer__textarea">
              <span>Metadata JSON</span>
              <textarea
                v-model="updateComposer.metadataJson"
                rows="3"
                placeholder="JSON object"
              />
            </label>
            <label class="topology-composer__notes">
              <span>Route notes</span>
              <input v-model="updateComposer.notes" type="text" placeholder="Update declarative route notes" />
            </label>
          </div>

          <div class="topology-inspector__actions">
            <button class="action-chip" type="button" :disabled="mutating" @click="stageRouteUpdate()">
              Stage route update
            </button>
            <button class="action-chip action-chip--danger" type="button" :disabled="mutating" @click="stageRouteDelete()">
              Stage route delete
            </button>
          </div>
        </div>

        <div v-else-if="inspectorMode === 'route' && selectedDraftDiffItem" class="topology-inspector__block">
          <div class="panel-heading">
            <span>Draft-only change</span>
            <span>{{ diffDescriptor(selectedDraftDiffItem) }}</span>
          </div>
          <dl class="system-grid">
            <div>
              <dt>Route key</dt>
              <dd>{{ selectedDraftDiffItem.route_key }}</dd>
            </div>
            <div>
              <dt>Event</dt>
              <dd>
                {{
                  readRecordValue(selectedDraftDiffItem.after, "event_type") ??
                  readRecordValue(selectedDraftDiffItem.before, "event_type") ??
                  parseRouteKey(selectedDraftDiffItem.route_key).eventType ??
                  "unknown"
                }}
              </dd>
            </div>
            <div>
              <dt>Consumer</dt>
              <dd>
                {{
                  readRecordValue(selectedDraftDiffItem.after, "consumer_key") ??
                  readRecordValue(selectedDraftDiffItem.before, "consumer_key") ??
                  parseRouteKey(selectedDraftDiffItem.route_key).consumerKey ??
                  "unknown"
                }}
              </dd>
            </div>
            <div>
              <dt>Change</dt>
              <dd>{{ selectedDraftDiffItem.change_type }}</dd>
            </div>
          </dl>
          <p class="surface-state">
            This route change exists in the active draft but is not yet in the live topology.
          </p>
        </div>

        <div v-else-if="inspectorMode === 'event' && selectedEventDefinition" class="topology-inspector__block">
          <div class="panel-heading">
            <span>Event registry</span>
            <span
              class="status-pill"
              :class="selectedEventDefinition.is_control_event ? 'status-pill--syncing' : 'status-pill--ok'"
            >
              {{ selectedEventDefinition.is_control_event ? "Control" : "Runtime" }}
            </span>
          </div>
          <p class="surface-state">{{ selectedEventDefinition.description }}</p>
          <dl class="system-grid">
            <div>
              <dt>Domain</dt>
              <dd>{{ selectedEventDefinition.domain }}</dd>
            </div>
            <div>
              <dt>Compatible consumers</dt>
              <dd>{{ selectedEventCompatibleConsumers.length }}</dd>
            </div>
            <div>
              <dt>Live routes</dt>
              <dd>{{ selectedEventRoutes.length }}</dd>
            </div>
            <div>
              <dt>Filter fields</dt>
              <dd>{{ routingHintFields(selectedEventDefinition) }}</dd>
            </div>
          </dl>

          <div class="topology-inspector__list">
            <div class="panel-heading">
              <span>Compatible consumers</span>
              <span>{{ selectedEventCompatibleConsumers.length }}</span>
            </div>
            <div v-if="selectedEventCompatibleConsumers.length === 0" class="surface-state">
              No compatible consumers registered for this event.
            </div>
            <button
              v-for="consumer in selectedEventCompatibleConsumers"
              :key="consumer.consumer_key"
              class="topology-diff__item"
              type="button"
              @click="selectConsumer(consumer.consumer_key)"
            >
              <strong>{{ consumer.display_name }}</strong>
              <small>{{ consumer.consumer_key }}</small>
            </button>
          </div>

          <div class="topology-inspector__list">
            <div class="panel-heading">
              <span>Recent audit</span>
              <span>{{ selectedEventAudit.length }}</span>
            </div>
            <div v-if="selectedEventAudit.length === 0" class="surface-state">
              No recent audit entries for this event.
            </div>
            <button
              v-for="entry in selectedEventAudit"
              :key="entry.id"
              class="topology-diff__item"
              type="button"
              @click="selectAuditEntry(entry)"
            >
              <strong>{{ entry.action }}</strong>
              <small>{{ formatDateTime(entry.created_at) }}</small>
            </button>
          </div>
        </div>

        <div v-else-if="inspectorMode === 'consumer' && selectedConsumerDefinition" class="topology-inspector__block">
          <div class="panel-heading">
            <span>Consumer registry</span>
            <span :class="`status-pill status-pill--${selectedConsumerMetrics?.dead ? 'down' : 'ok'}`">
              {{ selectedConsumerMetrics?.dead ? "Dead" : "Live" }}
            </span>
          </div>
          <p class="surface-state">{{ selectedConsumerDefinition.description }}</p>
          <dl class="system-grid">
            <div>
              <dt>Domain</dt>
              <dd>{{ selectedConsumerDefinition.domain }}</dd>
            </div>
            <div>
              <dt>Delivery</dt>
              <dd>{{ selectedConsumerDefinition.delivery_mode }}</dd>
            </div>
            <div>
              <dt>Stream</dt>
              <dd>{{ selectedConsumerDefinition.delivery_stream }}</dd>
            </div>
            <div>
              <dt>Shadow</dt>
              <dd>{{ selectedConsumerDefinition.supports_shadow ? "supported" : "not supported" }}</dd>
            </div>
            <div>
              <dt>Live routes</dt>
              <dd>{{ selectedConsumerRoutes.length }}</dd>
            </div>
            <div>
              <dt>Filter fields</dt>
              <dd>{{ listLabel(selectedConsumerDefinition.supported_filter_fields_json) }}</dd>
            </div>
          </dl>

          <div class="topology-inspector__metrics">
            <div class="indicator-card">
              <span>Processed</span>
              <strong>{{ selectedConsumerMetrics?.processed_total ?? 0 }}</strong>
            </div>
            <div class="indicator-card">
              <span>Failures</span>
              <strong>{{ selectedConsumerMetrics?.failure_count ?? 0 }}</strong>
            </div>
            <div class="indicator-card">
              <span>Lag</span>
              <strong>{{ formatDurationSeconds(selectedConsumerMetrics?.lag_seconds ?? null) }}</strong>
            </div>
          </div>

          <div class="topology-inspector__list">
            <div class="panel-heading">
              <span>Compatible events</span>
              <span>{{ selectedConsumerDefinition.compatible_event_types_json.length }}</span>
            </div>
            <button
              v-for="eventType in selectedConsumerDefinition.compatible_event_types_json"
              :key="eventType"
              class="topology-diff__item"
              type="button"
              @click="selectEvent(eventType)"
            >
              <strong>{{ eventType }}</strong>
              <small>{{ selectedConsumerDefinition.display_name }}</small>
            </button>
          </div>
        </div>

        <div v-else class="surface-state">
          Select an event, route, or consumer to inspect registry metadata, route rules, and live observability.
        </div>
      </aside>
    </section>

    <section class="surface-card topology-audit">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Audit stream</p>
          <h3>Recent control-plane changes</h3>
        </div>
        <p>{{ auditEntries.length }} recent entries</p>
      </div>

      <div v-if="auditEntries.length === 0" class="surface-state">No control-plane audit entries available.</div>
      <div v-else class="topology-audit__list">
        <button
          v-for="entry in auditEntries"
          :key="entry.id"
          class="topology-audit__item"
          type="button"
          @click="selectAuditEntry(entry)"
        >
          <div class="topology-audit__copy">
            <strong>{{ entry.action }}</strong>
            <p>{{ auditHeadline(entry) }}</p>
            <small>{{ formatDateTime(entry.created_at) }} · {{ entry.actor }} · {{ entry.actor_mode }}</small>
          </div>
          <div class="topology-audit__meta">
            <span class="pill pill--subtle">{{ entry.reason ?? "no reason" }}</span>
            <small>{{ auditContextLabel(entry) }}</small>
          </div>
        </button>
      </div>
    </section>
  </section>
</template>
