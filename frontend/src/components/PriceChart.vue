<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";

import type { CandleInterval, PriceHistoryPoint } from "../services/api";
import { formatCompactNumber } from "../utils/format";

const props = defineProps<{
  points: PriceHistoryPoint[];
  symbol: string;
  interval: CandleInterval;
}>();

const chartRoot = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;

function renderChart() {
  if (!chartRoot.value) {
    return;
  }

  if (!chart) {
    chart = echarts.init(chartRoot.value);
  }

  chart.setOption({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(7, 18, 28, 0.92)",
      borderColor: "rgba(148, 163, 184, 0.18)",
      textStyle: {
        color: "#e2e8f0",
      },
    },
    grid: {
      left: 18,
      right: 18,
      top: 24,
      bottom: 18,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: props.points.map((point) => new Date(point.timestamp).toLocaleString()),
      axisLine: { lineStyle: { color: "rgba(148, 163, 184, 0.25)" } },
      axisLabel: { color: "#7dd3c8", hideOverlap: true },
    },
    yAxis: [
      {
        type: "value",
        axisLine: { show: true, lineStyle: { color: "rgba(148, 163, 184, 0.25)" } },
        splitLine: { lineStyle: { color: "rgba(125, 211, 200, 0.08)" } },
        axisLabel: {
          color: "#94a3b8",
          formatter: (value: number) => `$${value.toLocaleString()}`,
        },
      },
      {
        type: "value",
        axisLabel: {
          color: "#64748b",
          formatter: (value: number) => formatCompactNumber(value),
        },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: props.symbol,
        type: "line",
        smooth: true,
        showSymbol: false,
        data: props.points.map((point) => point.price),
        lineStyle: {
          color: "#f59e0b",
          width: 3,
        },
        areaStyle: {
          color: "rgba(245, 158, 11, 0.14)",
        },
      },
      {
        name: "Volume",
        type: "bar",
        yAxisIndex: 1,
        data: props.points.map((point) => point.volume ?? 0),
        barMaxWidth: 6,
        itemStyle: {
          color: "rgba(45, 212, 191, 0.24)",
          borderRadius: [3, 3, 0, 0],
        },
      },
    ],
  });
}

function handleResize() {
  chart?.resize();
}

onMounted(() => {
  renderChart();
  window.addEventListener("resize", handleResize);
});

watch(
  () => props.points,
  () => {
    renderChart();
  },
  { deep: true },
);

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  chart?.dispose();
  chart = null;
});
</script>

<template>
  <div class="chart-shell">
    <div class="chart-shell__header">
      <div>
        <p class="chart-shell__eyebrow">{{ symbol }}</p>
        <h3>Close price with volume overlay</h3>
      </div>
      <span class="pill">{{ interval }}</span>
    </div>
    <div ref="chartRoot" class="h-[360px] w-full" />
  </div>
</template>
