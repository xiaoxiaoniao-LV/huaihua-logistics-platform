<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts'
import {
  getStatsOverview, getStatsResources, getStatsTrend,
  type ResourceStat, type StatsOverview, type TrendPoint,
} from '@/api/stats'
import { useAuthStore } from '@/stores/auth'
import { apiError } from '@/utils/error'

const auth = useAuthStore()

const overview = ref<StatsOverview | null>(null)
const trend = ref<TrendPoint[]>([])
const resourceStats = ref<ResourceStat[]>([])
const days = ref(7)
const loading = ref(false)
const error = ref('')

const trendRef = ref<HTMLDivElement | null>(null)
const resourceRef = ref<HTMLDivElement | null>(null)
let trendChart: echarts.ECharts | null = null
let resourceChart: echarts.ECharts | null = null

const axisStyle = {
  axisLine: { lineStyle: { color: 'rgba(64,158,255,0.25)' } },
  axisLabel: { color: 'rgba(240,245,255,0.5)', fontSize: 10 },
}

function ensureCharts() {
  if (trendRef.value && !trendChart) trendChart = echarts.init(trendRef.value, 'dark')
  if (resourceRef.value && !resourceChart) resourceChart = echarts.init(resourceRef.value, 'dark')
}

function renderTrend() {
  if (!trendChart) return
  trendChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10,26,54,0.9)',
      borderColor: 'rgba(64,158,255,0.5)',
      textStyle: { color: '#f0f5ff', fontSize: 11 },
    },
    legend: { data: ['订单数', '成交额', '佣金'], textStyle: { color: 'rgba(240,245,255,0.7)', fontSize: 11 }, top: 0 },
    grid: { left: 50, right: 55, top: 34, bottom: 28 },
    xAxis: { type: 'category', data: trend.value.map((d) => d.date.slice(5)), ...axisStyle, splitLine: { show: false } },
    yAxis: [
      { type: 'value', name: '单', ...axisStyle, splitLine: { lineStyle: { color: 'rgba(64,158,255,0.08)' } } },
      { type: 'value', name: '元', ...axisStyle, splitLine: { show: false } },
    ],
    series: [
      { name: '订单数', type: 'bar', barWidth: 14, itemStyle: { color: 'rgba(64,158,255,0.55)' }, data: trend.value.map((d) => d.orders) },
      { name: '成交额', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'circle', symbolSize: 5, lineStyle: { color: '#00e5ff', width: 2 }, itemStyle: { color: '#00e5ff' }, data: trend.value.map((d) => d.amount) },
      { name: '佣金', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'none', lineStyle: { color: '#ff9f43', width: 2, type: 'dashed' }, data: trend.value.map((d) => d.commission) },
    ],
  })
  trendChart.resize()
}

function renderResources() {
  if (!resourceChart) return
  resourceChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(10,26,54,0.9)',
      borderColor: 'rgba(64,158,255,0.5)',
      textStyle: { color: '#f0f5ff', fontSize: 11 },
    },
    legend: { data: ['可预约', '已预约', '其他'], textStyle: { color: 'rgba(240,245,255,0.7)', fontSize: 11 }, top: 0 },
    grid: { left: 60, right: 20, top: 34, bottom: 28 },
    xAxis: { type: 'category', data: resourceStats.value.map((r) => r.name), ...axisStyle },
    yAxis: { type: 'value', ...axisStyle, splitLine: { lineStyle: { color: 'rgba(64,158,255,0.08)' } } },
    series: [
      { name: '可预约', type: 'bar', stack: 'total', barWidth: 26, itemStyle: { color: '#00ff88' }, data: resourceStats.value.map((r) => r.available) },
      { name: '已预约', type: 'bar', stack: 'total', itemStyle: { color: '#ff9f43' }, data: resourceStats.value.map((r) => r.booked) },
      {
        name: '其他', type: 'bar', stack: 'total', itemStyle: { color: 'rgba(64,158,255,0.45)' },
        data: resourceStats.value.map((r) => Math.max(0, r.total - r.available - r.booked)),
      },
    ],
  })
  resourceChart.resize()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [ov, tr, rs] = await Promise.all([
      getStatsOverview(),
      getStatsTrend(days.value),
      getStatsResources(),
    ])
    overview.value = ov.data
    trend.value = tr.data.items
    resourceStats.value = rs.data.items
    await nextTick()
    ensureCharts()
    renderTrend()
    renderResources()
  } catch (e) {
    error.value = apiError(e, '加载统计数据失败')
  } finally {
    loading.value = false
  }
}

function switchDays(d: number) {
  days.value = d
  load()
}

function handleResize() {
  trendChart?.resize()
  resourceChart?.resize()
}

onMounted(async () => {
  if (!auth.user) await auth.fetchMe()
  if (!auth.isAdmin) return
  await load()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  resourceChart?.dispose()
  trendChart = null
  resourceChart = null
})
</script>

<template>
  <div class="page-scroll">
    <div v-if="!auth.isAdmin" class="panel">
      <div class="empty">该页面仅管理员可访问</div>
    </div>

    <template v-else>
      <div class="toolbar">
        <div class="filters">
          <button
            v-for="d in [7, 14, 30]"
            :key="d"
            class="btn btn-sm"
            :class="days === d ? '' : 'btn-ghost'"
            @click="switchDays(d)"
          >
            近 {{ d }} 天
          </button>
        </div>
        <span class="spacer"></span>
        <button class="btn btn-ghost btn-sm" :disabled="loading" @click="load">
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
      </div>

      <div v-if="error" class="error-text">{{ error }}</div>

      <div class="kpis">
        <div class="kpi">
          <div class="kpi-value">¥{{ (overview?.revenue.finished_amount ?? 0).toFixed(2) }}</div>
          <div class="kpi-label">累计成交额</div>
        </div>
        <div class="kpi">
          <div class="kpi-value orange">¥{{ (overview?.revenue.commission ?? 0).toFixed(2) }}</div>
          <div class="kpi-label">平台佣金</div>
        </div>
        <div class="kpi">
          <div class="kpi-value">{{ overview?.orders.finished ?? 0 }}</div>
          <div class="kpi-label">完成订单</div>
        </div>
        <div class="kpi">
          <div class="kpi-value">{{ overview?.revenue.avg_order_value ?? 0 }}</div>
          <div class="kpi-label">客单价（元）</div>
        </div>
        <div class="kpi">
          <div class="kpi-value green">{{ overview?.resources.available ?? 0 }}</div>
          <div class="kpi-label">可预约资源（共 {{ overview?.resources.total ?? 0 }}）</div>
        </div>
        <div class="kpi">
          <div class="kpi-value">{{ overview?.devices.online ?? 0 }}/{{ overview?.devices.total ?? 0 }}</div>
          <div class="kpi-label">在线设备</div>
        </div>
        <div class="kpi">
          <div class="kpi-value red">{{ overview?.alerts.active ?? 0 }}</div>
          <div class="kpi-label">待处理告警</div>
        </div>
        <div class="kpi">
          <div class="kpi-value">{{ overview?.reviews.avg_rating ?? 0 }}</div>
          <div class="kpi-label">平均评分</div>
        </div>
      </div>

      <div class="charts">
        <div class="panel chart-panel">
          <div class="panel-title">近 {{ days }} 天订单与收入</div>
          <div ref="trendRef" class="chart"></div>
        </div>
        <div class="panel chart-panel">
          <div class="panel-title">资源供给与占用</div>
          <div ref="resourceRef" class="chart"></div>
        </div>
      </div>

      <div class="panel" style="margin-top: 16px">
        <div class="panel-title">资源类型经营情况</div>
        <div class="panel-body">
          <table class="table">
            <thead>
              <tr>
                <th>类型</th>
                <th>总量</th>
                <th>可预约</th>
                <th>已预约</th>
                <th>待审核</th>
                <th>占用率</th>
                <th>累计成交额</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in resourceStats" :key="r.type">
                <td>{{ r.name }}</td>
                <td class="mono">{{ r.total }}</td>
                <td class="mono" style="color: var(--accent-green)">{{ r.available }}</td>
                <td class="mono" style="color: var(--accent-orange)">{{ r.booked }}</td>
                <td class="mono muted">{{ r.pending }}</td>
                <td class="mono">{{ (r.utilization * 100).toFixed(1) }}%</td>
                <td class="mono">¥{{ r.finished_amount.toFixed(2) }}</td>
              </tr>
              <tr v-if="!resourceStats.length">
                <td colspan="7"><div class="empty">{{ loading ? '加载中…' : '暂无数据' }}</div></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.filters { display: flex; gap: 6px; }
.kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.kpi {
  background: var(--bg-card);
  border: 1px solid var(--border-glow);
  border-radius: 8px;
  padding: 14px 16px;
  backdrop-filter: blur(10px);
}
.kpi-value {
  font-size: 22px;
  font-weight: 700;
  font-family: 'Consolas', 'Monaco', monospace;
  color: var(--accent-cyan);
}
.kpi-value.orange { color: var(--accent-orange); }
.kpi-value.green { color: var(--accent-green); }
.kpi-value.red { color: var(--accent-red); }
.kpi-label { font-size: 11px; color: var(--text-muted); margin-top: 6px; }

.charts { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }
.chart-panel { padding-bottom: 8px; }
.chart { width: 100%; height: 280px; }

@media (max-width: 1100px) {
  .kpis { grid-template-columns: repeat(2, 1fr); }
  .charts { grid-template-columns: 1fr; }
}
</style>
