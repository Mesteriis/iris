<script setup lang="ts">
import { reactive } from "vue";

import { useCoinStore } from "../../../stores/coinStore";
import {
  formatDateTime,
  formatDurationSeconds,
  formatRateLimitPolicy,
} from "../../../utils/format";

const coinStore = useCoinStore();
const addCoinForm = reactive({
  symbol: "",
  name: "",
  asset_type: "",
  theme: "",
  source: "",
  enabled: true,
  sort_order: "",
});

async function submitCoinForm() {
  const created = await coinStore.createCoin({
    symbol: addCoinForm.symbol.trim(),
    name: addCoinForm.name.trim(),
    asset_type: addCoinForm.asset_type.trim() || undefined,
    theme: addCoinForm.theme.trim() || undefined,
    source: addCoinForm.source.trim() || undefined,
    enabled: addCoinForm.enabled,
    sort_order: addCoinForm.sort_order === "" ? undefined : Number(addCoinForm.sort_order),
  });

  if (!created) {
    return;
  }

  addCoinForm.symbol = "";
  addCoinForm.name = "";
  addCoinForm.asset_type = "";
  addCoinForm.theme = "";
  addCoinForm.source = "";
  addCoinForm.enabled = true;
  addCoinForm.sort_order = "";
}

async function runCoinJob(symbol: string) {
  await coinStore.runCoinJob(symbol, "auto", true);
}
</script>

<template>
  <section class="detail-grid__row">
    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Add asset</p>
          <h3>Create tracked coin</h3>
        </div>
        <p>Submitting a new coin triggers backend backfill immediately.</p>
      </div>

      <form class="form-grid" @submit.prevent="submitCoinForm">
        <label class="field">
          <span>Symbol</span>
          <input v-model.trim="addCoinForm.symbol" placeholder="Enter symbol" required type="text" />
        </label>
        <label class="field">
          <span>Name</span>
          <input v-model.trim="addCoinForm.name" placeholder="Enter name" required type="text" />
        </label>
        <label class="field">
          <span>Asset type</span>
          <input v-model.trim="addCoinForm.asset_type" placeholder="Optional" type="text" />
        </label>
        <label class="field">
          <span>Theme</span>
          <input v-model.trim="addCoinForm.theme" placeholder="Optional" type="text" />
        </label>
        <label class="field">
          <span>Source</span>
          <input v-model.trim="addCoinForm.source" placeholder="Optional" type="text" />
        </label>
        <label class="field">
          <span>Sort order</span>
          <input v-model="addCoinForm.sort_order" min="0" step="1" placeholder="Optional" type="number" />
        </label>
        <label class="field field--checkbox">
          <input v-model="addCoinForm.enabled" type="checkbox" />
          <span>Enabled for sync</span>
        </label>
        <div class="form-actions">
          <button class="action-chip" :disabled="coinStore.isCreatingCoin" type="submit">
            {{ coinStore.isCreatingCoin ? "Creating..." : "Add coin" }}
          </button>
          <p v-if="coinStore.createCoinSuccess" class="form-message form-message--ok">
            {{ coinStore.createCoinSuccess }}
          </p>
          <p v-else-if="coinStore.createCoinError" class="form-message form-message--error">
            {{ coinStore.createCoinError }}
          </p>
        </div>
      </form>
    </article>

    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Background jobs</p>
          <h3>Backfill and sync state</h3>
        </div>
        <button class="action-chip" type="button" @click="coinStore.refreshDashboard()">Refresh jobs</button>
      </div>

      <div class="job-summary-grid">
        <div class="indicator-card">
          <span>Ready</span>
          <strong>{{ coinStore.jobStatusCounts.ready }}</strong>
        </div>
        <div class="indicator-card">
          <span>Backfilling</span>
          <strong>{{ coinStore.jobStatusCounts.backfilling }}</strong>
        </div>
        <div class="indicator-card">
          <span>Queued</span>
          <strong>{{ coinStore.jobStatusCounts.queued }}</strong>
        </div>
        <div class="indicator-card">
          <span>Retry</span>
          <strong>{{ coinStore.jobStatusCounts.retry_scheduled }}</strong>
        </div>
        <div class="indicator-card">
          <span>Error</span>
          <strong>{{ coinStore.jobStatusCounts.error }}</strong>
        </div>
      </div>

      <p v-if="coinStore.jobRunSuccess" class="form-message form-message--ok">
        {{ coinStore.jobRunSuccess }}
      </p>
      <p v-else-if="coinStore.jobRunError" class="form-message form-message--error">
        {{ coinStore.jobRunError }}
      </p>

      <ul class="detail-signal-list">
        <li v-for="entry in coinStore.jobStatusRows.slice(0, 8)" :key="entry.coin.symbol">
          <div>
            <strong>{{ entry.coin.symbol }}</strong>
            <p>{{ entry.job.detail }}</p>
          </div>
          <div class="detail-signal-list__meta">
            <span class="job-badge" :class="`job-badge--${entry.job.state}`">{{ entry.job.label }}</span>
            <small>{{ formatDateTime(entry.job.timestamp) }}</small>
            <button
              class="action-chip action-chip--compact"
              :disabled="coinStore.isJobRunning(entry.coin.symbol)"
              type="button"
              @click="runCoinJob(entry.coin.symbol)"
            >
              {{ coinStore.isJobRunning(entry.coin.symbol) ? "Queueing..." : "Run now" }}
            </button>
          </div>
        </li>
      </ul>
    </article>

    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Source cooldowns</p>
          <h3>Provider throttle state</h3>
        </div>
        <button class="action-chip" type="button" @click="coinStore.refreshDashboard()">Refresh sources</button>
      </div>

      <div class="job-summary-grid">
        <div class="indicator-card">
          <span>Sources</span>
          <strong>{{ coinStore.sourceStatusCounts.total }}</strong>
        </div>
        <div class="indicator-card">
          <span>Cooling</span>
          <strong>{{ coinStore.sourceStatusCounts.rateLimited }}</strong>
        </div>
        <div class="indicator-card">
          <span>Official caps</span>
          <strong>{{ coinStore.sourceStatusCounts.official }}</strong>
        </div>
        <div class="indicator-card">
          <span>Protective caps</span>
          <strong>{{ coinStore.sourceStatusCounts.protective }}</strong>
        </div>
      </div>

      <ul class="detail-signal-list">
        <li v-for="source in coinStore.sourceStatusRows" :key="source.name">
          <div>
            <strong>{{ source.name }}</strong>
            <p>
              {{ formatRateLimitPolicy(source.requests_per_window, source.window_seconds, source.request_cost) }}
              · {{ source.asset_types.join(", ") || "no assets" }}
            </p>
          </div>
          <div class="detail-signal-list__meta">
            <span class="source-badge" :class="`source-badge--${source.rate_limited ? 'limited' : 'live'}`">
              {{ source.rate_limited ? "Cooling down" : "Available" }}
            </span>
            <small>
              {{
                source.rate_limited
                  ? `next ${formatDateTime(source.next_available_at)}`
                  : source.min_interval_seconds
                    ? `${source.min_interval_seconds}s min gap`
                    : "No active cooldown"
              }}
            </small>
            <small class="source-limit-note">
              {{ source.official_limit ? "official policy" : "protective local cap" }}
              <template v-if="source.rate_limited">
                · {{ formatDurationSeconds(source.cooldown_seconds) }}
              </template>
            </small>
          </div>
        </li>
      </ul>
    </article>
  </section>
</template>
