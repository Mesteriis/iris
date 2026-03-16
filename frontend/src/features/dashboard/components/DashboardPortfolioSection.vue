<script setup lang="ts">
import { useCoinStore } from "../../../stores/coinStore";
import {
  formatCurrency,
  formatDateTime,
  formatMarketRegime,
  formatPercent,
} from "../../../utils/format";
import { decisionTone, formatFusionDecision } from "../lib/presentation";

const coinStore = useCoinStore();
</script>

<template>
  <section class="detail-grid__row">
    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Portfolio map</p>
          <h3>Capital allocation and live risk</h3>
        </div>
        <p>Portfolio Engine consumes fused market decisions without altering analytics layers.</p>
      </div>

      <div class="job-summary-grid">
        <div class="indicator-card">
          <span>Total capital</span>
          <strong>{{ formatCurrency(coinStore.portfolioState?.total_capital ?? null) }}</strong>
        </div>
        <div class="indicator-card">
          <span>Allocated</span>
          <strong>{{ formatCurrency(coinStore.portfolioState?.allocated_capital ?? null) }}</strong>
        </div>
        <div class="indicator-card">
          <span>Available</span>
          <strong>{{ formatCurrency(coinStore.portfolioState?.available_capital ?? null) }}</strong>
        </div>
        <div class="indicator-card">
          <span>Unrealized P/L</span>
          <strong :class="{ positive: coinStore.portfolioPnl > 0, negative: coinStore.portfolioPnl < 0 }">
            {{ formatCurrency(coinStore.portfolioPnl) }}
          </strong>
        </div>
        <div class="indicator-card">
          <span>Risk budget</span>
          <strong>{{ formatCurrency(coinStore.portfolioRiskBudget) }}</strong>
        </div>
      </div>

      <div v-if="coinStore.topPortfolioPositions.length === 0" class="surface-state">
        Portfolio Engine has not opened positions yet.
      </div>
      <ul v-else class="detail-signal-list">
        <li v-for="position in coinStore.topPortfolioPositions" :key="`portfolio-${position.id}`">
          <div>
            <strong>{{ position.symbol }}</strong>
            <p>
              {{ position.source_exchange || "No exchange" }} / {{ formatMarketRegime(position.regime) }}
              / {{ formatCurrency(position.position_value) }}
            </p>
          </div>
          <div class="detail-signal-list__meta">
            <span class="trend-badge" :class="`trend-badge--${decisionTone(position.latest_decision)}`">
              {{ formatFusionDecision(position.latest_decision) }}
            </span>
            <small :class="{ positive: position.unrealized_pnl > 0, negative: position.unrealized_pnl < 0 }">
              {{ formatCurrency(position.unrealized_pnl) }}
            </small>
            <small>risk {{ formatPercent((position.risk_to_stop ?? 0) * 100, 1) }}</small>
          </div>
        </li>
      </ul>
    </article>

    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Portfolio watch radar</p>
          <h3>Held coins in IRIS context</h3>
        </div>
        <p>Shows portfolio assets together with their regime, fused decision and downside risk.</p>
      </div>

      <div v-if="coinStore.portfolioWatchRadar.length === 0" class="surface-state">
        No watched portfolio coins are available yet.
      </div>
      <ul v-else class="detail-signal-list">
        <li v-for="item in coinStore.portfolioWatchRadar.slice(0, 8)" :key="`watch-${item.symbol}`">
          <div>
            <strong>{{ item.symbol }}</strong>
            <p>
              {{ item.sourceExchange || "No exchange" }} / {{ formatMarketRegime(item.regime) }}
              / {{ formatCurrency(item.positionValue) }}
            </p>
          </div>
          <div class="detail-signal-list__meta">
            <span class="trend-badge" :class="`trend-badge--${decisionTone(item.latestDecision)}`">
              {{ formatFusionDecision(item.latestDecision) }}
            </span>
            <small>{{ formatPercent((item.latestDecisionConfidence ?? 0) * 100, 1) }}</small>
            <small :class="{ positive: item.unrealizedPnl > 0, negative: item.unrealizedPnl < 0 }">
              {{ formatCurrency(item.unrealizedPnl) }}
            </small>
          </div>
        </li>
      </ul>
    </article>

    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Portfolio actions</p>
          <h3>Latest execution intents</h3>
        </div>
        <p>{{ coinStore.latestPortfolioActions.length }} latest actions from Portfolio Engine.</p>
      </div>

      <div v-if="coinStore.latestPortfolioActions.length === 0" class="surface-state">
        No portfolio actions have been generated yet.
      </div>
      <ul v-else class="detail-signal-list">
        <li v-for="action in coinStore.latestPortfolioActions" :key="`portfolio-action-${action.id}`">
          <div>
            <strong>{{ action.symbol }}</strong>
            <p>{{ action.action.replace(/_/g, " ") }} / {{ action.market_decision }}</p>
          </div>
          <div class="detail-signal-list__meta">
            <span>{{ formatCurrency(action.size) }}</span>
            <small>{{ formatPercent(action.confidence * 100, 1) }}</small>
            <small>{{ formatDateTime(action.created_at) }}</small>
          </div>
        </li>
      </ul>
    </article>
  </section>
</template>
