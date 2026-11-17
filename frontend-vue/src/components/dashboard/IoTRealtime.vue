<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { useIoTStore } from '@/stores/iot'
import { theme } from '@/config/theme'
import { ECHARTS_THEME } from '@/config/echartsTheme'

const iot = useIoTStore()
const chartRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

const axisName = { color: theme.color.text.muted, fontSize: theme.font.xs }

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value, ECHARTS_THEME)
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 46, right: 16, top: 24, bottom: 24 },
    xAxis: {
      type: 'time',
      axisLabel: {
        formatter: (v: number) => new Date(v).toLocaleTimeString('zh-CN', { hour12: false }),
      },
    },
    yAxis: [
      { name: '温度℃', type: 'value', nameTextStyle: axisName },
      { name: '湿度%', type: 'value', min: 0, max: 100, nameTextStyle: axisName, splitLine: { show: false } },
    ],
    series: [
      {
        name: '温度', type: 'line', smooth: true, symbol: 'none',
        lineStyle: { color: theme.color.accent.cyan, width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(0,229,255,0.28)' },
            { offset: 1, color: 'rgba(0,229,255,0)' },
          ]),
        },
        data: [] as [number, number][],
      },
      {
        name: '湿度', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'none',
        lineStyle: { color: theme.color.accent.amber, width: 2 },
        data: [] as [number, number][],
      },
    ],
  })
}

function updateChart() {
  if (!chart) return
  // 取 timeline 最近 60 条（约 1 分钟内）
  const recent = iot.timeline.slice(-60)
  const temp: [number, number][] = []
  const hum: [number, number][] = []
  for (const d of recent) {
    const t = new Date(d.recorded_at).getTime()
    if (d.temperature != null) temp.push([t, d.temperature])
    if (d.humidity != null) hum.push([t, d.humidity])
  }
  chart.setOption({ series: [{ data: temp }, { data: hum }] })
}

function handleResize() { chart?.resize() }

watch(() => iot.timeline.length, () => { nextTick(updateChart) })

onMounted(async () => {
  await nextTick()
  initChart()
  updateChart()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="panel panel--secondary iot-panel">
    <div class="panel-title">IoT 实时监测</div>
    <div class="panel-body">
      <div ref="chartRef" class="chart-box"></div>
    </div>
  </div>
</template>

<style scoped>
.iot-panel { display: flex; flex-direction: column; }
.iot-panel > .panel-body {
  flex: 1 1 auto;
  min-height: 0;
  padding-bottom: var(--space-2);
}
.chart-box { width: 100%; height: 100%; min-height: 120px; }
</style>
