<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts'
import {
  getStatsOverview, getStatsResources, getStatsTrend,
  type ResourceStat, type StatsOverview, type TrendPoint,
} from '@/api/stats'
import { useAuthStore } from '@/stores/auth'
import { apiError } from '@/utils/error'
import { theme } from '@/config/theme'
import { ECHARTS_THEME } from '@/config/echartsTheme'
import {
  getInvoicePdf, getReconciliation, getSettlementSplit, listSettlements, updateSettlementStatus,
  type Reconciliation, type Settlement, type SettlementSplit,
} from '@/api/settlements'

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
  axisLine: { lineStyle: { color: theme.color.border.soft } },
  axisLabel: { color: theme.color.text.muted, fontSize: theme.font.xs },
}

function ensureCharts() {
  if (trendRef.value && !trendChart) trendChart = echarts.init(trendRef.value, ECHARTS_THEME)
  if (resourceRef.value && !resourceChart) resourceChart = echarts.init(resourceRef.value, ECHARTS_THEME)
}

function renderTrend() {
  if (!trendChart) return
  trendChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['订单数', '成交额', '佣金'], top: 0 },
    grid: { left: 50, right: 55, top: 34, bottom: 28 },
    xAxis: { type: 'category', data: trend.value.map((d) => d.date.slice(5)), ...axisStyle, splitLine: { show: false } },
    yAxis: [
      { type: 'value', name: '单', ...axisStyle },
      { type: 'value', name: '元', ...axisStyle, splitLine: { show: false } },
    ],
    series: [
      { name: '订单数', type: 'bar', barWidth: 14, itemStyle: { color: 'rgba(64,158,255,0.55)' }, data: trend.value.map((d) => d.orders) },
      { name: '成交额', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'circle', symbolSize: 5, lineStyle: { color: theme.color.accent.cyan, width: 2 }, itemStyle: { color: theme.color.accent.cyan }, data: trend.value.map((d) => d.amount) },
      { name: '佣金', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'none', lineStyle: { color: theme.color.accent.amber, width: 2, type: 'dashed' }, data: trend.value.map((d) => d.commission) },
    ],
  })
  trendChart.resize()
}

function renderResources() {
  if (!resourceChart) return
  resourceChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['可预约', '已预约', '其他'], top: 0 },
    grid: { left: 60, right: 20, top: 34, bottom: 28 },
    xAxis: { type: 'category', data: resourceStats.value.map((r) => r.name), ...axisStyle },
    yAxis: { type: 'value', ...axisStyle },
    series: [
      { name: '可预约', type: 'bar', stack: 'total', barWidth: 26, itemStyle: { color: theme.color.status.available }, data: resourceStats.value.map((r) => r.available) },
      { name: '已预约', type: 'bar', stack: 'total', itemStyle: { color: theme.color.status.booked }, data: resourceStats.value.map((r) => r.booked) },
      {
        name: '其他', type: 'bar', stack: 'total', itemStyle: { color: theme.color.status.offline },
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

// ---------- 结算与对账 ----------
const recon = ref<Reconciliation | null>(null)
const settlements = ref<Settlement[]>([])
const settleStatus = ref('')
const settleLoading = ref(false)
const settleError = ref('')
const settlingId = ref<number | null>(null)
const invoicingId = ref<number | null>(null)
const split = ref<SettlementSplit | null>(null)

const settleLabels: Record<string, string> = {
  pending: '待确认', confirmed: '已确认', paid: '已打款', void: '已作废',
}
const settleTag: Record<string, string> = {
  pending: 'tag-orange', confirmed: 'tag-blue', paid: 'tag-green', void: 'tag-red',
}

function money(v?: number | string | null) {
  if (v == null || v === '') return '-'
  return `¥${Number(v).toFixed(2)}`
}

async function loadSettlements() {
  settleLoading.value = true
  settleError.value = ''
  try {
    const [reconResp, listResp, splitResp] = await Promise.all([
      getReconciliation(),
      listSettlements({ status: settleStatus.value || undefined, page: 1, page_size: 50 }),
      getSettlementSplit(),
    ])
    recon.value = reconResp.data
    settlements.value = listResp.data
    split.value = splitResp.data
  } catch (e) {
    settleError.value = apiError(e, '加载结算数据失败')
  } finally {
    settleLoading.value = false
  }
}

async function moveSettlement(s: Settlement, next: string, confirmText: string) {
  if (!window.confirm(confirmText)) return
  settleError.value = ''
  settlingId.value = s.id
  try {
    await updateSettlementStatus(s.id, next)
    await loadSettlements()
  } catch (e) {
    settleError.value = apiError(e, '更新结算状态失败')
  } finally {
    settlingId.value = null
  }
}

async function downloadInvoice(s: Settlement) {
  invoicingId.value = s.id
  settleError.value = ''
  try {
    const resp = await getInvoicePdf(s.id)
    const url = URL.createObjectURL(new Blob([resp.data], { type: 'application/pdf' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `invoice-${s.id}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    settleError.value = apiError(e, '下载发票失败')
  } finally {
    invoicingId.value = null
  }
}

function handleResize() {
  trendChart?.resize()
  resourceChart?.resize()
}

function refreshAll() {
  load()
  loadSettlements()
}

onMounted(async () => {
  if (!auth.user) await auth.fetchMe()
  if (!auth.isAdmin) return
  await Promise.all([load(), loadSettlements()])
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
        <button class="btn btn-ghost btn-sm" :disabled="loading || settleLoading" @click="refreshAll">
          {{ loading || settleLoading ? '刷新中…' : '刷新' }}
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
                <td class="mono" style="color: var(--status-available)">{{ r.available }}</td>
                <td class="mono" style="color: var(--status-booked)">{{ r.booked }}</td>
                <td class="mono" style="color: var(--status-pending)">{{ r.pending }}</td>
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

      <div class="panel" style="margin-top: 16px" data-guide="settlement-panel">
        <div class="panel-title">结算与对账</div>
        <div class="panel-body">
          <div v-if="settleError" class="error-text">{{ settleError }}</div>

          <div class="recon">
            <div class="recon-item">
              <div class="recon-value">{{ recon?.orders ?? 0 }}</div>
              <div class="recon-label">{{ recon?.day || '今日' }} 订单数</div>
            </div>
            <div class="recon-item">
              <div class="recon-value">{{ money(recon?.gmv) }}</div>
              <div class="recon-label">当日 GMV</div>
            </div>
            <div class="recon-item">
              <div class="recon-value orange">{{ money(recon?.commission) }}</div>
              <div class="recon-label">当日佣金</div>
            </div>
            <div class="recon-item">
              <div class="recon-value green">{{ money(recon?.paid_amount) }}</div>
              <div class="recon-label">当日回款</div>
            </div>
            <div class="recon-item">
              <div class="recon-value">{{ recon?.pending_settlements ?? 0 }}</div>
              <div class="recon-label">待打款结算单</div>
            </div>
            <div class="recon-item">
              <div class="recon-value orange">{{ money(recon?.pending_payout) }}</div>
              <div class="recon-label">待打款金额</div>
            </div>
          </div>

          <div class="toolbar" style="margin: 12px 0 8px">
            <div class="filters">
              <button
                v-for="opt in [
                  { v: '', t: '全部' },
                  { v: 'pending', t: '待确认' },
                  { v: 'confirmed', t: '已确认' },
                  { v: 'paid', t: '已打款' },
                  { v: 'void', t: '已作废' },
                ]"
                :key="opt.v"
                class="btn btn-sm"
                :class="settleStatus === opt.v ? '' : 'btn-ghost'"
                @click="settleStatus = opt.v; loadSettlements()"
              >
                {{ opt.t }}
              </button>
            </div>
          </div>

          <table class="table">
            <thead>
              <tr>
                <th>结算单</th>
                <th>订单</th>
                <th>供给方</th>
                <th>订单金额</th>
                <th>佣金</th>
                <th>应付供给方</th>
                <th>状态</th>
                <th style="width: 200px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in settlements" :key="s.id">
                <td class="mono muted">#{{ s.id }}</td>
                <td class="mono">#{{ s.order_id }}</td>
                <td class="mono">#{{ s.supplier_id }}</td>
                <td class="mono">{{ money(s.amount) }}</td>
                <td class="mono" style="color: var(--accent-orange)">
                  {{ money(s.commission) }}（{{ (Number(s.commission_rate) * 100).toFixed(1) }}%）
                </td>
                <td class="mono">{{ money(s.payable_to_supplier) }}</td>
                <td>
                  <span class="tag" :class="settleTag[s.status] || 'tag-blue'">
                    {{ settleLabels[s.status] || s.status }}
                  </span>
                </td>
                <td>
                  <template v-if="settlingId === s.id">
                    <span class="muted" style="font-size: 12px">处理中…</span>
                  </template>
                  <template v-else>
                    <button
                      v-if="s.status === 'pending'"
                      class="btn btn-sm"
                      @click="moveSettlement(s, 'confirmed', '确认该结算单金额无误？')"
                    >
                      确认
                    </button>
                    <button
                      v-if="s.status === 'confirmed'"
                      class="btn btn-sm"
                      @click="moveSettlement(s, 'paid', '确认已向供给方打款？')"
                    >
                      标记已打款
                    </button>
                    <button
                      v-if="s.status === 'pending' || s.status === 'confirmed'"
                      class="btn btn-danger btn-sm"
                      @click="moveSettlement(s, 'void', '确认作废该结算单？')"
                    >
                      作废
                    </button>
                    <button
                      v-if="s.status !== 'void'"
                      class="btn btn-ghost btn-sm"
                      :disabled="invoicingId === s.id"
                      @click="downloadInvoice(s)"
                    >
                      {{ invoicingId === s.id ? '生成中…' : '凭证' }}
                    </button>
                    <span v-if="s.status === 'paid'" class="muted" style="font-size: 12px">
                      {{ s.settled_at ? s.settled_at.replace('T', ' ').slice(0, 16) : '已打款' }}
                    </span>
                    <span v-if="s.status === 'void'" class="muted" style="font-size: 12px">已作废</span>
                  </template>
                </td>
              </tr>
              <tr v-if="!settlements.length">
                <td colspan="8">
                  <div class="empty">{{ settleLoading ? '加载中…' : '暂无结算单（订单完成后自动生成）' }}</div>
                </td>
              </tr>
            </tbody>
          </table>

          <div class="panel-title" style="margin-top: 16px">租户分账（按供给方）</div>
          <table class="table">
            <thead>
              <tr>
                <th>供给方</th>
                <th>结算笔数</th>
                <th>订单金额</th>
                <th>佣金</th>
                <th>应付</th>
                <th>已付</th>
                <th>待付</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in split?.items || []" :key="r.supplier_id">
                <td>{{ r.supplier_name }}</td>
                <td class="mono">{{ r.settlements }}</td>
                <td class="mono">{{ money(r.amount) }}</td>
                <td class="mono" style="color: var(--accent-orange)">{{ money(r.commission) }}</td>
                <td class="mono">{{ money(r.payable) }}</td>
                <td class="mono" style="color: var(--status-available)">{{ money(r.paid) }}</td>
                <td class="mono" style="color: var(--status-pending)">{{ money(r.unpaid) }}</td>
              </tr>
              <tr v-if="split && split.items.length">
                <td class="muted">合计</td>
                <td class="mono">{{ split.total.settlements }}</td>
                <td class="mono">{{ money(split.total.amount) }}</td>
                <td class="mono">{{ money(split.total.commission) }}</td>
                <td class="mono">{{ money(split.total.payable) }}</td>
                <td class="mono">{{ money(split.total.paid) }}</td>
                <td class="mono">{{ money(split.total.unpaid) }}</td>
              </tr>
              <tr v-if="!split || !split.items.length">
                <td colspan="7"><div class="empty">暂无分账数据</div></td>
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
  font-size: var(--fs-xl);
  font-weight: 700;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--accent-cyan);
}
.kpi-value.orange { color: var(--accent-orange); }
.kpi-value.green { color: var(--status-available); }
.kpi-value.red { color: var(--accent-red); }
.kpi-label { font-size: var(--fs-xs); color: var(--text-muted); margin-top: 6px; }

.recon {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 10px;
}
.recon-item {
  background: rgba(64, 158, 255, 0.05);
  border: 1px solid var(--border-glow);
  border-radius: 6px;
  padding: 10px 12px;
}
.recon-value {
  font-size: var(--fs-lg);
  font-weight: 700;
  font-family: var(--font-mono);
  color: var(--accent-cyan);
}
.recon-value.orange { color: var(--accent-orange); }
.recon-value.green { color: var(--status-available); }
.recon-label { font-size: var(--fs-xs); color: var(--text-muted); margin-top: 4px; }

.charts { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }
.chart-panel { padding-bottom: 8px; }
.chart { width: 100%; height: 280px; }

@media (max-width: 1100px) {
  .kpis { grid-template-columns: repeat(2, 1fr); }
  .charts { grid-template-columns: 1fr; }
  .recon { grid-template-columns: repeat(3, 1fr); }
}
</style>
