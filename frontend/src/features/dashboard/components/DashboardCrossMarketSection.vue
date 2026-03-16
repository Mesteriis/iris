<script setup lang="ts">
import { useCoinStore } from "../../../stores/coinStore";
import {
  formatActivityBucket,
  formatCompactNumber,
  formatCurrencyDelta,
  formatDateTime,
  formatMarketRegime,
  formatPercent,
  timeframeToLabel,
} from "../../../utils/format";
import { predictionTone } from "../lib/presentation";

const coinStore = useCoinStore();
</script>

<template>
  <section class="detail-grid__row">
    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Market flow map</p>
          <h3>Leaders and followers</h3>
        </div>
        <p>Cross-market intelligence tracks who is leading and who is absorbing the move.</p>
      </div>

      <div class="job-summary-grid">
        <div class="indicator-card">
          <span>Leaders</span>
          <strong>{{ coinStore.marketFlowLeaders.length }}</strong>
        </div>
        <div class="indicator-card">
          <span>Relations</span>
          <strong>{{ coinStore.marketFlowRelations.length }}</strong>
        </div>
        <div class="indicator-card">
          <span>Rotations</span>
          <strong>{{ coinStore.marketFlowRotations.length }}</strong>
        </div>
        <div class="indicator-card">
          <span>Sectors</span>
          <strong>{{ coinStore.marketFlowSectors.length }}</strong>
        </div>
      </div>

      <div v-if="coinStore.marketFlowRelations.length === 0" class="surface-state">
        Cross-market relations have not been populated yet.
      </div>
      <ul v-else class="detail-signal-list">
        <li
          v-for="item in coinStore.marketFlowRelations.slice(0, 6)"
          :key="`flow-${item.leader_coin_id}-${item.follower_coin_id}`"
        >
          <div>
            <strong>{{ item.leader_symbol }} → {{ item.follower_symbol }}</strong>
            <p>lag {{ item.lag_hours }}h / updated {{ formatDateTime(item.updated_at) }}</p>
          </div>
          <div class="detail-signal-list__meta">
            <span>{{ formatPercent(item.correlation * 100, 1) }}</span>
            <small>{{ formatPercent(item.confidence * 100, 1) }}</small>
          </div>
        </li>
      </ul>
    </article>

    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Sector momentum</p>
          <h3>Rotation and capital flow</h3>
        </div>
        <p>Sector strength helps explain where follow-through is most likely to appear.</p>
      </div>

      <div v-if="coinStore.marketFlowSectors.length === 0" class="surface-state">
        Sector momentum snapshots are not available yet.
      </div>
      <ul v-else class="detail-signal-list">
        <li v-for="item in coinStore.marketFlowSectors.slice(0, 4)" :key="`sector-flow-${item.sector_id}`">
          <div>
            <strong>{{ item.sector }}</strong>
            <p>
              {{ item.trend ?? "No trend data" }} / {{ formatPercent(item.avg_price_change_24h, 2) }}
              / vol {{ formatPercent(item.avg_volume_change_24h, 2) }}
            </p>
          </div>
          <div class="detail-signal-list__meta">
            <span>{{ formatPercent(item.relative_strength, 2) }}</span>
            <small>{{ formatCompactNumber(item.capital_flow) }}</small>
            <small>{{ formatDateTime(item.updated_at) }}</small>
          </div>
        </li>
        <li
          v-for="rotation in coinStore.marketFlowRotations.slice(0, 3)"
          :key="`rotation-${rotation.source_sector}-${rotation.target_sector}-${rotation.timestamp}`"
        >
          <div>
            <strong>{{ rotation.source_sector }} → {{ rotation.target_sector }}</strong>
            <p>{{ timeframeToLabel(rotation.timeframe) }} rotation event</p>
          </div>
          <div class="detail-signal-list__meta">
            <span class="trend-badge trend-badge--sideways">rotation</span>
            <small>{{ formatDateTime(rotation.timestamp) }}</small>
          </div>
        </li>
      </ul>
    </article>

    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Prediction journal</p>
          <h3>Follow-through memory</h3>
        </div>
        <p>IRIS keeps score on cross-market predictions and exposes whether they actually worked.</p>
      </div>

      <div v-if="coinStore.predictionJournal.length === 0" class="surface-state">
        No tracked predictions yet.
      </div>
      <ul v-else class="detail-signal-list">
        <li v-for="item in coinStore.predictionJournal.slice(0, 6)" :key="`prediction-${item.id}`">
          <div>
            <strong>{{ item.leader_symbol }} → {{ item.target_symbol }}</strong>
            <p>
              {{ item.prediction_event.replace(/_/g, " ") }} / {{ item.expected_move }}
              / lag {{ item.lag_hours }}h
            </p>
          </div>
          <div class="detail-signal-list__meta">
            <span class="trend-badge" :class="`trend-badge--${predictionTone(item.status)}`">
              {{ item.status }}
            </span>
            <small>{{ formatPercent(item.confidence * 100, 1) }}</small>
            <small>{{ item.profit === null ? "pending" : formatPercent(item.profit * 100, 2) }}</small>
          </div>
        </li>
      </ul>
    </article>
  </section>

  <section class="detail-grid__row">
    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Market radar</p>
          <h3>HOT and emerging coins</h3>
        </div>
        <p>Dynamic scheduling highlights the assets that deserve immediate pattern analysis.</p>
      </div>

      <div class="job-summary-grid">
        <div class="indicator-card">
          <span>HOT now</span>
          <strong>{{ coinStore.hotRadarCoins.length }}</strong>
        </div>
        <div class="indicator-card">
          <span>Emerging</span>
          <strong>{{ coinStore.emergingRadarCoins.length }}</strong>
        </div>
        <div class="indicator-card">
          <span>Regime flips</span>
          <strong>{{ coinStore.regimeChangeRadar.length }}</strong>
        </div>
        <div class="indicator-card">
          <span>Volatility spikes</span>
          <strong>{{ coinStore.volatilitySpikeRadar.length }}</strong>
        </div>
      </div>

      <ul class="detail-signal-list">
        <li v-for="row in coinStore.hotRadarCoins.slice(0, 4)" :key="`hot-${row.symbol}`">
          <div>
            <strong>{{ row.symbol }}</strong>
            <p>
              {{ formatActivityBucket(row.activity_bucket) }} · {{ formatMarketRegime(row.market_regime) }}
            </p>
          </div>
          <div class="detail-signal-list__meta">
            <span class="trend-badge trend-badge--bullish">{{ formatCompactNumber(row.activity_score) }}</span>
            <small>{{ formatDateTime(row.last_analysis_at ?? row.updated_at) }}</small>
          </div>
        </li>
        <li v-for="row in coinStore.emergingRadarCoins.slice(0, 4)" :key="`emerging-${row.symbol}`">
          <div>
            <strong>{{ row.symbol }}</strong>
            <p>24h {{ formatCurrencyDelta(row.price_change_24h) }} · 7d {{ formatCurrencyDelta(row.price_change_7d) }}</p>
          </div>
          <div class="detail-signal-list__meta">
            <span class="trend-badge trend-badge--sideways">{{ formatMarketRegime(row.market_regime) }}</span>
            <small>{{ formatDateTime(row.updated_at) }}</small>
          </div>
        </li>
      </ul>
    </article>

    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Regime pulse</p>
          <h3>Regime changes and volatility spikes</h3>
        </div>
        <p>Redis Stream events expose context shifts without rescanning full history.</p>
      </div>

      <ul class="detail-signal-list">
        <li
          v-for="row in coinStore.regimeChangeRadar.slice(0, 4)"
          :key="`regime-${row.symbol}-${row.timeframe}-${row.timestamp}`"
        >
          <div>
            <strong>{{ row.symbol }}</strong>
            <p>{{ timeframeToLabel(row.timeframe) }} · {{ formatMarketRegime(row.regime) }}</p>
          </div>
          <div class="detail-signal-list__meta">
            <span class="trend-badge trend-badge--sideways">{{ formatPercent(row.confidence * 100, 0) }}</span>
            <small>{{ formatDateTime(row.timestamp) }}</small>
          </div>
        </li>
        <li v-for="row in coinStore.volatilitySpikeRadar.slice(0, 4)" :key="`volatility-${row.symbol}`">
          <div>
            <strong>{{ row.symbol }}</strong>
            <p>{{ formatMarketRegime(row.market_regime) }} · 24h {{ formatCurrencyDelta(row.price_change_24h) }}</p>
          </div>
          <div class="detail-signal-list__meta">
            <span class="trend-badge trend-badge--bearish">{{ formatCompactNumber(row.volatility) }}</span>
            <small>{{ formatDateTime(row.updated_at) }}</small>
          </div>
        </li>
      </ul>
    </article>
  </section>
</template>
