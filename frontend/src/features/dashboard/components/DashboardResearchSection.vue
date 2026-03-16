<script setup lang="ts">
import { useCoinStore } from "../../../stores/coinStore";
import {
  formatDateTime,
  formatMarketRegime,
  formatPercent,
  formatSignalType,
  timeframeToLabel,
} from "../../../utils/format";

const coinStore = useCoinStore();
</script>

<template>
  <section class="surface-card">
    <div class="section-head">
      <div>
        <p class="section-head__eyebrow">Self evolving strategies</p>
        <h3>Top discovered combinations</h3>
      </div>
      <p>{{ coinStore.strategies.length }} stored strategies</p>
    </div>

    <div v-if="coinStore.topStrategies.length === 0" class="surface-state">
      Strategy discovery has not produced ranked strategies yet.
    </div>
    <ul v-else class="detail-signal-list">
      <li v-for="strategy in coinStore.topStrategies" :key="strategy.strategy_id">
        <div>
          <strong>{{ strategy.name }}</strong>
          <p>
            win {{ formatPercent(strategy.win_rate * 100, 2) }}
            / ret {{ formatPercent(strategy.avg_return * 100, 2) }}
            / dd {{ formatPercent(strategy.max_drawdown * 100, 2) }}
          </p>
        </div>
        <div class="detail-signal-list__meta">
          <span>{{ strategy.sharpe_ratio.toFixed(2) }}</span>
          <small>sample {{ strategy.sample_size }}</small>
          <small>{{ strategy.enabled ? "enabled" : "disabled" }}</small>
        </div>
      </li>
    </ul>
  </section>

  <section class="surface-card">
    <div class="section-head">
      <div>
        <p class="section-head__eyebrow">Backtest engine</p>
        <h3>Signals with proven edge</h3>
      </div>
      <p>{{ coinStore.topBacktests.length }} ranked signal stacks</p>
    </div>

    <div v-if="coinStore.topBacktests.length === 0" class="surface-state">
      Backtest engine has not produced signal performance rows yet.
    </div>
    <ul v-else class="detail-signal-list">
      <li v-for="item in coinStore.topBacktests" :key="`${item.signal_type}-${item.timeframe}`">
        <div>
          <strong>{{ formatSignalType(item.signal_type) }}</strong>
          <p>
            {{ timeframeToLabel(item.timeframe) }} / win {{ formatPercent(item.win_rate * 100, 2) }}
            / avg {{ formatPercent(item.avg_return * 100, 2) }}
          </p>
        </div>
        <div class="detail-signal-list__meta">
          <span>{{ item.sharpe_ratio.toFixed(2) }}</span>
          <small>ROI {{ formatPercent(item.roi * 100, 2) }}</small>
          <small>sample {{ item.sample_size }}</small>
        </div>
      </li>
    </ul>
  </section>

  <section class="surface-card">
    <div class="section-head">
      <div>
        <p class="section-head__eyebrow">Pattern health</p>
        <h3>Success engine dashboard</h3>
      </div>
      <p>{{ coinStore.activePatternsCount }} active / {{ coinStore.disabledPatternsCount }} disabled</p>
    </div>

    <div class="job-summary-grid">
      <div class="indicator-card">
        <span>Tracked patterns</span>
        <strong>{{ coinStore.patterns.length }}</strong>
      </div>
      <div class="indicator-card">
        <span>Active</span>
        <strong>{{ coinStore.activePatternsCount }}</strong>
      </div>
      <div class="indicator-card">
        <span>Disabled</span>
        <strong>{{ coinStore.disabledPatternsCount }}</strong>
      </div>
      <div class="indicator-card">
        <span>Regime edges</span>
        <strong>{{ coinStore.patternRegimeEfficiency.length }}</strong>
      </div>
    </div>

    <div class="detail-grid__row">
      <article class="surface-card surface-card--nested">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Top patterns</p>
            <h3>Rolling success window</h3>
          </div>
          <p>Last 200 mature signals per scope</p>
        </div>

        <ul class="detail-signal-list">
          <li v-for="row in coinStore.patternHealthRows.slice(0, 8)" :key="`health-${row.slug}`">
            <div>
              <strong>{{ formatSignalType(row.slug) }}</strong>
              <p>{{ row.category }} / {{ row.lifecycleState }} / {{ row.totalSignals }} signals</p>
            </div>
            <div class="detail-signal-list__meta">
              <span>{{ formatPercent(row.successRate * 100, 2) }}</span>
              <small>avg {{ formatPercent(row.avgReturn * 100, 2) }}</small>
              <small>temp {{ row.hottestTemperature.toFixed(3) }}</small>
            </div>
          </li>
        </ul>
      </article>

      <article class="surface-card surface-card--nested">
        <div class="section-head">
          <div>
            <p class="section-head__eyebrow">Regime efficiency</p>
            <h3>Best pattern-by-regime fits</h3>
          </div>
          <p>Regime-aware success rows</p>
        </div>

        <ul class="detail-signal-list">
          <li
            v-for="row in coinStore.patternRegimeEfficiency"
            :key="`pattern-regime-${row.slug}-${row.market_regime}`"
          >
            <div>
              <strong>{{ formatSignalType(row.slug) }}</strong>
              <p>{{ formatMarketRegime(row.market_regime) }} / sample {{ row.total_signals }}</p>
            </div>
            <div class="detail-signal-list__meta">
              <span>{{ formatPercent(row.success_rate * 100, 2) }}</span>
              <small>{{ row.enabled ? "enabled" : "suppressed" }}</small>
            </div>
          </li>
        </ul>
      </article>
    </div>
  </section>

  <section class="surface-card">
    <div class="section-head">
      <div>
        <p class="section-head__eyebrow">Pattern library</p>
        <h3>Lifecycle and temperature</h3>
      </div>
      <p>{{ coinStore.patterns.length }} registered detectors</p>
    </div>

    <ul class="detail-signal-list">
      <li v-for="pattern in coinStore.patterns.slice(0, 12)" :key="pattern.slug">
        <div>
          <strong>{{ formatSignalType(pattern.slug) }}</strong>
          <p>{{ pattern.category }} / {{ pattern.lifecycle_state }}</p>
        </div>
        <div class="detail-signal-list__meta">
          <span>
            {{
              pattern.statistics.length > 0
                ? Math.max(...pattern.statistics.map((item) => item.temperature)).toFixed(3)
                : "0.000"
            }}
          </span>
          <small>CPU {{ pattern.cpu_cost }}</small>
        </div>
      </li>
    </ul>
  </section>

  <section class="detail-grid__row">
    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Feature flags</p>
          <h3>Subsystem switches</h3>
        </div>
        <p>{{ coinStore.enabledPatternFeatures.length }} enabled</p>
      </div>

      <ul class="detail-signal-list">
        <li v-for="feature in coinStore.patternFeatures" :key="feature.feature_slug">
          <div>
            <strong>{{ formatSignalType(feature.feature_slug) }}</strong>
            <p>{{ formatDateTime(feature.created_at) }}</p>
          </div>
          <div class="detail-signal-list__meta">
            <span>{{ feature.enabled ? "enabled" : "disabled" }}</span>
          </div>
        </li>
      </ul>
    </article>

    <article class="surface-card">
      <div class="section-head">
        <div>
          <p class="section-head__eyebrow">Discovery</p>
          <h3>Review candidates</h3>
        </div>
        <p>{{ coinStore.discoveredPatterns.length }} candidates</p>
      </div>

      <ul v-if="coinStore.discoveredPatterns.length > 0" class="detail-signal-list">
        <li
          v-for="candidate in coinStore.discoveredPatterns.slice(0, 10)"
          :key="`${candidate.structure_hash}-${candidate.timeframe}`"
        >
          <div>
            <strong>{{ candidate.structure_hash.slice(0, 12) }}</strong>
            <p>{{ timeframeToLabel(candidate.timeframe) }} / sample {{ candidate.sample_size }}</p>
          </div>
          <div class="detail-signal-list__meta">
            <span>{{ candidate.confidence.toFixed(3) }}</span>
            <small>
              ret {{ formatPercent(candidate.avg_return * 100, 2) }} / dd {{ formatPercent(candidate.avg_drawdown * 100, 2) }}
            </small>
          </div>
        </li>
      </ul>
      <div v-else class="surface-state">Discovery engine has not produced review candidates yet.</div>
    </article>
  </section>
</template>
