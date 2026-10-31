<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { listResources, type Resource } from '@/api/resources'
import { createOrder } from '@/api/orders'
import AppModal from '@/components/common/AppModal.vue'
import { apiError } from '@/utils/error'

const typeLabels: Record<string, string> = {
  warehouse: '仓库', cold_box: '冷链箱', vehicle: '运力', equipment: '设备',
}
const statusLabels: Record<string, string> = {
  available: '可预约', booked: '已预约', pending: '待审核', offline: '已下架',
}
const statusTag: Record<string, string> = {
  available: 'tag-green', booked: 'tag-orange', pending: 'tag-blue', offline: 'tag-red',
}

const items = ref<Resource[]>([])
const loading = ref(false)
const typeFilter = ref('')
const keyword = ref('')

// 服务端分页
const page = ref(1)
const pageSize = 10
const total = ref(0)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

const list = computed(() => items.value)

async function load() {
  loading.value = true
  try {
    const resp = await listResources({
      status: 'available',
      type: typeFilter.value || undefined,
      keyword: keyword.value.trim() || undefined,
      page: page.value,
      page_size: pageSize,
    })
    items.value = resp.data
    total.value = Number(resp.headers['x-total-count'] ?? resp.data.length)
    // 删除/审核等导致当前页为空时回退一页
    if (!items.value.length && page.value > 1) {
      page.value -= 1
      await load()
    }
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  load()
}

function goto(p: number) {
  if (p < 1 || p > totalPages.value || p === page.value) return
  page.value = p
  load()
}

// ---------- 下单 ----------
const ordering = ref<Resource | null>(null)
const submitting = ref(false)
const orderError = ref('')
const orderForm = reactive({ start: '', end: '' })

/** datetime-local 值（2026-10-31T10:00）转后端需要的本地时间字符串 */
function toLocalIso(v: string): string {
  if (!v) return ''
  return v.length === 16 ? `${v}:00` : v
}

const estimatedDays = computed(() => {
  if (!orderForm.start || !orderForm.end) return 0
  const s = new Date(orderForm.start).getTime()
  const e = new Date(orderForm.end).getTime()
  if (!(e > s)) return 0
  return Math.ceil((e - s) / 86400000)
})
const estimatedPrice = computed(() => {
  const r = ordering.value
  if (!r || !r.price || !estimatedDays.value) return null
  return (Number(r.price) * estimatedDays.value).toFixed(2)
})

function openOrder(r: Resource) {
  ordering.value = r
  orderError.value = ''
  const now = new Date()
  const start = new Date(now.getTime() + 3600 * 1000)
  const end = new Date(start.getTime() + 86400 * 1000)
  const fmt = (d: Date) => {
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
  }
  orderForm.start = fmt(start)
  orderForm.end = fmt(end)
}

async function submitOrder() {
  if (!ordering.value) return
  orderError.value = ''
  if (!orderForm.start || !orderForm.end) {
    orderError.value = '请选择起止时间'
    return
  }
  if (new Date(orderForm.end) <= new Date(orderForm.start)) {
    orderError.value = '结束时间必须晚于开始时间'
    return
  }
  submitting.value = true
  try {
    await createOrder({
      resource_id: ordering.value.id,
      start_time: toLocalIso(orderForm.start),
      end_time: toLocalIso(orderForm.end),
    })
    ordering.value = null
    await load()
  } catch (e) {
    orderError.value = apiError(e, '下单失败')
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-scroll">
    <div class="toolbar">
      <select v-model="typeFilter" class="select" style="width: 160px" @change="applyFilters">
        <option value="">全部类型</option>
        <option v-for="(label, key) in typeLabels" :key="key" :value="key">{{ label }}</option>
      </select>
      <input
        v-model="keyword"
        class="input"
        style="width: 220px"
        placeholder="搜索资源名称，回车查询"
        @keyup.enter="applyFilters"
      />
      <span class="muted" style="font-size: 12px">共 {{ total }} 条可预约资源</span>
      <span class="spacer"></span>
      <button class="btn btn-ghost btn-sm" :disabled="loading" @click="load">
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
    </div>

    <div class="panel">
      <table class="table">
        <thead>
          <tr>
            <th>资源名称</th>
            <th>类型</th>
            <th>位置</th>
            <th>价格</th>
            <th>状态</th>
            <th style="width: 90px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in list" :key="r.id">
            <td>{{ r.name }}</td>
            <td class="muted">{{ typeLabels[r.type] || r.type }}</td>
            <td class="muted">{{ r.location || '-' }}</td>
            <td class="mono" style="color: var(--accent-orange)">
              {{ r.price != null ? `¥${r.price}/${r.price_unit || '天'}` : '-' }}
            </td>
            <td>
              <span class="tag" :class="statusTag[r.status] || 'tag-blue'">
                {{ statusLabels[r.status] || r.status }}
              </span>
            </td>
            <td>
              <button class="btn btn-sm" @click="openOrder(r)">预约</button>
            </td>
          </tr>
          <tr v-if="!list.length">
            <td colspan="6">
              <div class="empty">{{ loading ? '加载中…' : '暂无可预约资源' }}</div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pager">
      <span>第 {{ page }} / {{ totalPages }} 页</span>
      <button class="btn btn-ghost btn-sm" :disabled="page <= 1 || loading" @click="goto(page - 1)">上一页</button>
      <button class="btn btn-ghost btn-sm" :disabled="page >= totalPages || loading" @click="goto(page + 1)">下一页</button>
    </div>

    <AppModal v-if="ordering" title="预约资源" @close="ordering = null">
      <div class="summary">
        <div class="summary-name">{{ ordering.name }}</div>
        <div class="summary-meta">
          {{ typeLabels[ordering.type] || ordering.type }} · {{ ordering.location || '未填写位置' }}
        </div>
        <div v-if="ordering.price != null" class="summary-price">
          ¥{{ ordering.price }} / {{ ordering.price_unit || '天' }}
        </div>
      </div>

      <div class="field-row">
        <div class="field">
          <label class="field-label">开始时间</label>
          <input v-model="orderForm.start" class="input" type="datetime-local" />
        </div>
        <div class="field">
          <label class="field-label">结束时间</label>
          <input v-model="orderForm.end" class="input" type="datetime-local" />
        </div>
      </div>

      <div v-if="estimatedDays" class="estimate">
        预计 {{ estimatedDays }} 天
        <template v-if="estimatedPrice">，合计 <b>¥{{ estimatedPrice }}</b></template>
      </div>

      <div class="error-text">{{ orderError }}</div>

      <template #footer>
        <button class="btn btn-ghost" @click="ordering = null">取消</button>
        <button class="btn" :disabled="submitting" @click="submitOrder">
          {{ submitting ? '提交中…' : '确认预约' }}
        </button>
      </template>
    </AppModal>
  </div>
</template>

<style scoped>
.summary {
  background: rgba(64, 158, 255, 0.06);
  border: 1px solid var(--border-glow);
  border-radius: 6px;
  padding: 12px 14px;
  margin-bottom: 16px;
}
.summary-name { font-size: 14px; font-weight: 600; }
.summary-meta { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
.summary-price { font-size: 13px; color: var(--accent-orange); margin-top: 6px; font-family: 'Consolas', monospace; }
.estimate { font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }
.estimate b { color: var(--accent-orange); font-family: 'Consolas', monospace; }
</style>
