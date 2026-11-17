<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listResources, type Resource } from '@/api/resources'
import { listOrders, type Order } from '@/api/orders'
import { listAlerts, type IoTAlert } from '@/api/iot'
import { listDevices, type Device } from '@/api/devices'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const resources = ref<Resource[]>([])
const orders = ref<Order[]>([])
const alerts = ref<IoTAlert[]>([])
const devices = ref<Device[]>([])
const loading = ref(false)
const loadError = ref('')

const myResources = computed(() => resources.value.filter((r) => r.user_id === auth.user?.id))
const pendingReview = computed(() => myResources.value.filter((r) => r.status === 'pending'))
const availableCount = computed(() => myResources.value.filter((r) => r.status === 'available'))
const toConfirm = computed(() => orders.value.filter((o) => o.status === 'pending'))
const inProgress = computed(() => orders.value.filter((o) => o.status === 'confirmed' || o.status === 'ongoing'))
const onlineDevices = computed(() => devices.value.filter((d) => d.status === 'online'))

const kpis = computed(() => [
  { label: '已上架资源', value: availableCount.value, unit: '个', to: '/resources', tone: 'cyan' },
  { label: '待审核资源', value: pendingReview.value.length, unit: '个', to: '/resources', tone: 'blue' },
  { label: '待确认订单', value: toConfirm.value.length, unit: '单', to: '/orders', tone: 'orange' },
  { label: '履约中订单', value: inProgress.value.length, unit: '单', to: '/orders', tone: 'green' },
  { label: '活动告警', value: alerts.value.length, unit: '条', to: '/alerts', tone: 'red' },
  {
    label: '在线设备',
    value: onlineDevices.value.length,
    unit: `/ ${devices.value.length}`,
    to: '/devices',
    tone: 'cyan',
  },
])

const todos = computed(() => {
  const rows: { key: string; title: string; desc: string; tag: string; tagClass: string; to: string }[] = []
  for (const o of toConfirm.value.slice(0, 3)) {
    rows.push({
      key: `order-${o.id}`,
      title: `订单 #${o.id} 待确认`,
      desc: o.start_time ? `开始时间 ${o.start_time.slice(0, 16).replace('T', ' ')}` : '需求方已发起询价',
      tag: '去确认',
      tagClass: 'tag-orange',
      to: '/orders',
    })
  }
  for (const a of alerts.value.slice(0, 3)) {
    rows.push({
      key: `alert-${a.id}`,
      title: a.device_code ? `${a.device_code} 告警` : '设备告警',
      desc: a.message,
      tag: a.level === 'critical' ? '紧急' : '待处置',
      tagClass: a.level === 'critical' ? 'tag-red' : 'tag-orange',
      to: '/alerts',
    })
  }
  for (const r of pendingReview.value.slice(0, 2)) {
    rows.push({
      key: `res-${r.id}`,
      title: `资源「${r.name}」待审核`,
      desc: '管理员审核通过后将在资源市场上架',
      tag: '待审核',
      tagClass: 'tag-blue',
      to: '/resources',
    })
  }
  return rows
})

async function load() {
  loading.value = true
  loadError.value = ''
  await Promise.all([
    listResources({ page_size: 200 })
      .then(({ data }) => { resources.value = data })
      .catch(() => { resources.value = [] }),
    listOrders({ mine: 'supplier', page_size: 200 })
      .then(({ data }) => { orders.value = data })
      .catch(() => { orders.value = [] }),
    listAlerts({ status: 'active', limit: 20 })
      .then(({ data }) => { alerts.value = data.alerts })
      .catch(() => { alerts.value = [] }),
    listDevices()
      .then(({ data }) => { devices.value = data })
      .catch(() => { devices.value = [] }),
  ])
  loading.value = false
  if (!resources.value.length && !orders.value.length && !devices.value.length) {
    loadError.value = '部分数据加载失败，请确认后端服务与登录状态'
  }
}

onMounted(async () => {
  if (!auth.user) await auth.fetchMe()
  await load()
})
</script>

<template>
  <div class="page-scroll">
    <div class="toolbar">
      <span class="muted" style="font-size: 12px">
        当前身份：{{ auth.displayName || '未登录' }} · 信用分 {{ auth.user?.credit_score ?? '-' }}
      </span>
      <span class="spacer"></span>
      <button class="btn btn-ghost btn-sm" :disabled="loading" @click="load">
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
      <RouterLink to="/resources" class="btn btn-sm">发布资源</RouterLink>
    </div>

    <div v-if="loadError" class="error-text">{{ loadError }}</div>

    <div class="kpi-grid">
      <RouterLink v-for="k in kpis" :key="k.label" :to="k.to" class="kpi-card" :class="`kpi-${k.tone}`">
        <div class="kpi-label">{{ k.label }}</div>
        <div class="kpi-value">
          {{ k.value }}<span class="kpi-unit">{{ k.unit }}</span>
        </div>
      </RouterLink>
    </div>

    <div class="panel">
      <div class="panel-head">
        <span class="panel-title">今日待办</span>
        <span class="muted" style="font-size: 12px">共 {{ todos.length }} 项</span>
      </div>
      <div v-if="!todos.length" class="empty">
        {{ loading ? '加载中…' : '暂无待办，订单与告警均已处理' }}
      </div>
      <RouterLink v-for="t in todos" :key="t.key" :to="t.to" class="todo-row">
        <div class="todo-main">
          <div class="todo-title">{{ t.title }}</div>
          <div class="todo-desc">{{ t.desc }}</div>
        </div>
        <span class="tag" :class="t.tagClass">{{ t.tag }}</span>
      </RouterLink>
    </div>

    <div class="quick-grid">
      <RouterLink to="/market" class="quick-card">
        <div class="quick-title">资源市场</div>
        <div class="quick-desc">查看平台全部供给与撮合结果</div>
      </RouterLink>
      <RouterLink to="/orders" class="quick-card">
        <div class="quick-title">订单履约</div>
        <div class="quick-desc">确认、开始、完成与结算跟进</div>
      </RouterLink>
      <RouterLink to="/alerts" class="quick-card">
        <div class="quick-title">告警处置</div>
        <div class="quick-desc">处理冷链温湿度与设备异常</div>
      </RouterLink>
      <RouterLink to="/devices" class="quick-card">
        <div class="quick-title">设备管理</div>
        <div class="quick-desc">终端注册、绑定资源与遥测查询</div>
      </RouterLink>
      <RouterLink v-if="auth.isAdmin" to="/twin" class="quick-card">
        <div class="quick-title">孪生配置</div>
        <div class="quick-desc">空间树、孪生节点与点位绑定</div>
      </RouterLink>
      <RouterLink v-if="auth.isAdmin" to="/admin" class="quick-card">
        <div class="quick-title">审核与用户</div>
        <div class="quick-desc">资源上架审核与账号管理</div>
      </RouterLink>
    </div>
  </div>
</template>

<style scoped>
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}
.kpi-card {
  display: block;
  text-decoration: none;
  padding: 14px 16px;
  border-radius: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border-glow);
  transition: border-color 0.2s, transform 0.2s;
}
.kpi-card:hover { transform: translateY(-2px); }
.kpi-cyan:hover { border-color: var(--accent-cyan); }
.kpi-blue:hover { border-color: var(--accent); }
.kpi-orange:hover { border-color: var(--accent-orange); }
.kpi-green:hover { border-color: var(--accent-green); }
.kpi-red:hover { border-color: var(--accent-red); }
.kpi-label { font-size: 12px; color: var(--text-secondary); }
.kpi-value {
  margin-top: 8px;
  font-size: 26px;
  font-weight: 700;
  font-family: 'Consolas', monospace;
  color: var(--text-primary);
}
.kpi-unit { font-size: 12px; margin-left: 4px; color: var(--text-muted); font-weight: 400; }

.panel { margin-bottom: 14px; }
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle, rgba(120, 160, 220, 0.12));
}
.panel-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.todo-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  text-decoration: none;
  border-bottom: 1px solid var(--border-subtle, rgba(120, 160, 220, 0.08));
  transition: background 0.15s;
}
.todo-row:hover { background: rgba(0, 229, 255, 0.05); }
.todo-main { flex: 1; min-width: 0; }
.todo-title { font-size: 13px; color: var(--text-primary); }
.todo-desc {
  margin-top: 3px;
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}
.quick-card {
  display: block;
  padding: 16px;
  border-radius: 8px;
  text-decoration: none;
  background: linear-gradient(135deg, rgba(0, 229, 255, 0.06), rgba(10, 26, 54, 0.4));
  border: 1px solid var(--border-glow);
  transition: border-color 0.2s;
}
.quick-card:hover { border-color: var(--accent-cyan); }
.quick-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.quick-desc { margin-top: 6px; font-size: 12px; color: var(--text-muted); }
</style>
