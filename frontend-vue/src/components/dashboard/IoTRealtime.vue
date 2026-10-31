<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { useIoTStore } from '@/stores/iot'

const iot = useIoTStore()
const chartRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value, 'dark')
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 45, right: 15, top: 10, bottom: 28 },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: 'rgba(64,158,255,0.25)' } },
      axisLabel: { color: 'rgba(240,245,255,0.5)', fontSize: 10, formatter: (v: number) => new Date(v).toLocaleTimeString('zh-CN', { hour12: false }) },
      splitLine: { show: false },
    },
    yAxis: [
      { name: '温度℃', type: 'value', axisLine: { lineStyle: { color: 'rgba(64,158,255,0.25)' } }, axisLabel: { color: 'rgba(240,245,255,0.5)', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(64,158,255,0.08)' } } },
      { name: '湿度%', type: 'value', min: 0, max: 100, axisLine: { lineStyle: { color: 'rgba(255,159,67,0.25)' } }, axisLabel: { color: 'rgba(240,245,255,0.5)', fontSize: 10 }, splitLine: { show: false } },
    ],
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(10,26,54,0.9)', borderColor: 'rgba(64,158,255,0.5)', textStyle: { color: '#f0f5ff', fontSize: 11 } },
    series: [
      {
        name: '温度', type: 'line', smooth: true, symbol: 'none',
        lineStyle: { color: '#00e5ff', width: 2 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(0,229,255,0.3)' }, { offset: 1, color: 'rgba(0,229,255,0)' },
        ]) },
        data: [] as [number, number][],
      },
      {
        name: '湿度', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'none',
        lineStyle: { color: '#ff9f43', width: 2 },
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
  <div class="panel">
    <div class="panel-title">IoT 实时监测</div>
    <div class="panel-body">
      <div ref="chartRef" class="chart-box"></div>
    </div>
  </div>
</template>

<style scoped>
.chart-box { width: 100%; height: 180px; }
</style>
