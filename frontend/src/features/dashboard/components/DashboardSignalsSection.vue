<script setup lang="ts">
import { useCoinStore } from "../../../stores/coinStore";
import {
  formatDateTime,
  formatMarketRegime,
  formatPercent,
  formatSignalType,
  timeframeToLabel,
} from "../../../utils/format";
import { decisionTone, formatFusionDecision } from "../lib/presentation";

const coinStore = useCoinStore();
</script>

<template>
  <section class="detail-grid__row">
    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Decision radar</p>
          <h3>Unified BUY / SELL layer</h3>
        </div>
        <p>{{ coinStore.topMarketDecisionRadar.length }} fused decisions</p>
      </div>

      <div v-if="coinStore.topMarketDecisionRadar.length === 0" class="surface-state">
        Signal Fusion Engine has not produced market decisions yet.
      </div>
      <ul v-else class="detail-signal-list">
        <li v-for="item in coinStore.topMarketDecisionRadar" :key="`${item.symbol}-${item.timeframe}`">
          <div>
            <strong>{{ item.symbol }}</strong>
            <p>
              {{ timeframeToLabel(item.timeframe) }} / {{ formatMarketRegime(item.regime) }} / {{ item.signal_count }} signals
            </p>
          </div>
          <div class="detail-signal-list__meta">
            <span class="trend-badge" :class="`trend-badge--${decisionTone(item.decision)}`">
              {{ formatFusionDecision(item.decision) }}
            </span>
            <small>{{ formatPercent(item.confidence * 100, 2) }}</small>
            <small>{{ formatDateTime(item.created_at) }}</small>
          </div>
        </li>
      </ul>
    </article>

    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Top signals</p>
          <h3>Priority-ranked flow</h3>
        </div>
        <p>{{ coinStore.topSignals.length }} ranked items</p>
      </div>

      <div v-if="coinStore.topSignals.length === 0" class="surface-state">
        No prioritized signals yet.
      </div>
      <ul v-else class="detail-signal-list">
        <li v-for="signal in coinStore.topSignals" :key="signal.id">
          <div>
            <strong>{{ signal.symbol }} · {{ formatSignalType(signal.signal_type) }}</strong>
            <p>
              {{ timeframeToLabel(signal.timeframe) }} / {{ formatMarketRegime(signal.market_regime) }}
              <template v-if="signal.cycle_phase"> / {{ signal.cycle_phase }}</template>
              <template v-if="signal.cluster_membership.length > 0">
                / {{ signal.cluster_membership.map(formatSignalType).join(", ") }}
              </template>
            </p>
          </div>
          <div class="detail-signal-list__meta">
            <span>{{ signal.priority_score.toFixed(3) }}</span>
            <small>{{ Math.round(signal.confidence * 100) }}%</small>
          </div>
        </li>
      </ul>
    </article>

    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Sector rotation</p>
          <h3>Capital flow map</h3>
        </div>
        <p>{{ coinStore.sectors.length }} sectors from current taxonomy</p>
      </div>

      <div class="indicator-grid">
        <div
          v-for="item in coinStore.topSectorMetrics"
          :key="`${item.sector_id}-${item.timeframe}`"
          class="indicator-card"
        >
          <span>{{ item.name }} · {{ timeframeToLabel(item.timeframe) }}</span>
          <strong>{{ formatPercent(item.sector_strength * 100, 2) }}</strong>
          <small>
            RS {{ formatPercent(item.relative_strength * 100, 2) }} · Flow {{ item.capital_flow.toFixed(2) }}
          </small>
        </div>
      </div>

      <ul v-if="coinStore.sectorNarratives.length > 0" class="detail-signal-list">
        <li v-for="narrative in coinStore.sectorNarratives" :key="narrative.timeframe">
          <div>
            <strong>{{ timeframeToLabel(narrative.timeframe) }}</strong>
            <p>
              {{ narrative.top_sector || "No top sector" }}
              <template v-if="narrative.capital_wave">
                / wave {{ narrative.capital_wave }}
              </template>
            </p>
          </div>
          <div class="detail-signal-list__meta">
            <span>{{ narrative.rotation_state || "No rotation state" }}</span>
            <small>
              BTC dom
              {{
                narrative.btc_dominance !== null
                  ? `${(narrative.btc_dominance * 100).toFixed(1)}%`
                  : "No data"
              }}
            </small>
          </div>
        </li>
      </ul>
    </article>
  </section>
</template>
