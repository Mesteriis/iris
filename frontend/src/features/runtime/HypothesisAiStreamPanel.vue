<script setup lang="ts">
import { computed, onMounted } from "vue";

import { formatDateTime } from "../../utils/format";
import { useHypothesisAiStream } from "./useHypothesisAiStream";

const { connect, disconnect, events, lastReceivedAt, status } = useHypothesisAiStream();

const statusTone = computed(() => {
  if (status.value === "connected") {
    return "ok";
  }
  if (status.value === "connecting" || status.value === "reconnecting") {
    return "syncing";
  }
  return "down";
});

const statusLabel = computed(() => {
  if (status.value === "connected") {
    return "Live";
  }
  if (status.value === "connecting") {
    return "Connecting";
  }
  if (status.value === "reconnecting") {
    return "Reconnecting";
  }
  if (status.value === "error") {
    return "Error";
  }
  return "Idle";
});

onMounted(() => {
  connect();
});
</script>

<template>
  <section class="surface-card">
    <div class="section-head">
      <div>
        <p class="section-head__eyebrow">Live stream</p>
        <h3>Hypothesis SSE</h3>
      </div>
      <div class="table-action">
        <span class="status-pill" :class="`status-pill--${statusTone}`">{{ statusLabel }}</span>
        <button
          v-if="status !== 'connected'"
          class="action-chip"
          type="button"
          @click="connect()"
        >
          Connect
        </button>
        <button
          v-else
          class="action-chip action-chip--danger"
          type="button"
          @click="disconnect()"
        >
          Disconnect
        </button>
      </div>
    </div>

    <p class="surface-state">
      Frontend listens to the live AI stream on the existing backend SSE endpoint. When control
      plane routes publish hypothesis events, they will appear here without page refresh.
    </p>

    <div class="job-summary-grid">
      <div class="indicator-card">
        <span>Status</span>
        <strong>{{ statusLabel }}</strong>
      </div>
      <div class="indicator-card">
        <span>Buffered events</span>
        <strong>{{ events.length }}</strong>
      </div>
      <div class="indicator-card">
        <span>Last event</span>
        <strong>{{ formatDateTime(lastReceivedAt) }}</strong>
      </div>
    </div>

    <div v-if="events.length === 0" class="surface-state">
      Stream is connected, but no AI events have reached the frontend yet.
    </div>
    <ul v-else class="detail-signal-list">
      <li v-for="item in events" :key="item.id">
        <div>
          <strong>{{ item.type }}</strong>
          <p>
            coin {{ item.payload.coin_id ?? "NA" }} / timeframe {{ item.payload.timeframe ?? "NA" }}
          </p>
        </div>
        <div class="detail-signal-list__meta">
          <span>{{ formatDateTime(item.receivedAt) }}</span>
          <small>{{ item.payload.timestamp ?? "no payload timestamp" }}</small>
        </div>
      </li>
    </ul>
  </section>
</template>
