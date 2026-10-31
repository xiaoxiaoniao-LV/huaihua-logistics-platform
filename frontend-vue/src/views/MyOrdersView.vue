<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listOrders, updateOrderStatus, type Order } from '@/api/orders'
import { listResources, type Resource } from '@/api/resources'
import { createReview, listOrderReviews, type Review } from '@/api/reviews'
import { useAuthStore } from '@/stores/auth'
import AppModal from '@/components/common/AppModal.vue'
import { apiError } from '@/utils/error'

const auth = useAuthStore()

const statusLabels: Record<string, string> = {
  pending: '待确认', confirmed: '已确认', ongoing: '进行中', finished: '已完成', cancelled: '已取消',
}
const statusTag: Record<string, string> = {
  pending: 'tag-blue', confirmed: 'tag-green', ongoing: 'tag-green', finished: 'tag-green', cancelled: 'tag-red',
}

const orders = ref<Order[]>([])
const resourceMap = ref<Record<number, Resource>>({})
const loading = ref(false)
const actionError = ref('')
const busyId = ref<number | null>(null)

// 服务端分页
const page = ref(1)
const pageSize = 10
const total = ref(0)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

const isAdmin = computed(() => auth.user?.role === 'admin')

function isSupplierOf(o: Order) {
  return isAdmin.value || o.supplier_id === auth.user?.id
}
function isDemanderOf(o: Order) {
  return isAdmin.value || o.demander_id === auth.user?.id
}

async function load() {
  loading.value = true
  try {
    const [orderResp, resResp] = await Promise.all([
      listOrders({ page: page.value, page_size: pageSize }),
      listResources({ page: 1, page_size: 200 }),
    ])
    orders.value = orderResp.data
    total.value = Number(orderResp.headers['x-total-count'] ?? orderResp.data.length)
    const map: Record<number, Resource> = {}
    resResp.data.forEach((r: Resource) => (map[r.id] = r))
    resourceMap.value = map
    if (!orders.value.length && page.value > 1) {
      page.value -= 1
      await load()
    }
  } finally {
    loading.value = false
  }
}

function goto(p: number) {
  if (p < 1 || p > totalPages.value || p === page.value) return
  page.value = p
  load()
}

async function changeStatus(o: Order, status: string, confirmText?: string) {
  if (confirmText && !window.confirm(confirmText)) return
  actionError.value = ''
  busyId.value = o.id
  try {
    await updateOrderStatus(o.id, status)
    await load()
  } catch (e) {
    actionError.value = apiError(e, '操作失败')
  } finally {
    busyId.value = null
  }
}

// ---------- 评价 ----------
const reviewing = ref<Order | null>(null)
const reviews = ref<Review[]>([])
const reviewLoading = ref(false)
const rating = ref(5)
const content = ref('')
const reviewError = ref('')
const submittingReview = ref(false)

const myReview = computed(() => reviews.value.find((r) => r.from_user_id === auth.user?.id) || null)
const otherReview = computed(() => reviews.value.find((r) => r.from_user_id !== auth.user?.id) || null)

async function openReview(o: Order) {
  reviewing.value = o
  reviews.value = []
  reviewError.value = ''
  content.value = ''
  rating.value = 5
  reviewLoading.value = true
  try {
    const { data } = await listOrderReviews(o.id)
    reviews.value = data
  } catch (e) {
    reviewError.value = apiError(e, '加载评价失败')
  } finally {
    reviewLoading.value = false
  }
}

async function submitReview() {
  if (!reviewing.value) return
  reviewError.value = ''
  submittingReview.value = true
  try {
    await createReview({ order_id: reviewing.value.id, rating: rating.value, content: content.value || undefined })
    await openReview(reviewing.value)
    await load()
    await auth.fetchMe()
  } catch (e) {
    reviewError.value = apiError(e, '提交评价失败')
  } finally {
    submittingReview.value = false
  }
}

function fmtTime(v?: string | null) {
  if (!v) return '-'
  return v.replace('T', ' ').slice(0, 16)
}

// ---------- 账单明细 ----------
const billing = ref<Order | null>(null)

const billingResource = computed(() =>
  billing.value ? resourceMap.value[billing.value.resource_id] : undefined,
)

const billingDays = computed(() => {
  const o = billing.value
  if (!o?.start_time || !o?.end_time) return 0
  const s = new Date(o.start_time).getTime()
  const e = new Date(o.end_time).getTime()
  if (!(e > s)) return 0
  return Math.ceil((e - s) / 86400000)
})

const billingCommissionRate = computed(() => {
  const r = Number(billing.value?.commission_rate ?? 0)
  return `${(r * 100).toFixed(1)}%`
})

function money(v?: number | null) {
  return v == null ? '-' : `¥${Number(v).toFixed(2)}`
}

function openBilling(o: Order) {
  billing.value = o
}

onMounted(async () => {
  if (!auth.user) await auth.fetchMe()
  await load()
})
</script>

<template>
  <div class="page-scroll">
    <div class="toolbar">
      <span class="muted" style="font-size: 12px">共 {{ total }} 个订单</span>
      <span class="spacer"></span>
      <button class="btn btn-ghost btn-sm" :disabled="loading" @click="load">
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
    </div>

    <div v-if="actionError" class="error-text">{{ actionError }}</div>

    <div class="panel">
      <table class="table">
        <thead>
          <tr>
            <th>订单号</th>
            <th>资源</th>
            <th>时段</th>
            <th>金额</th>
            <th>状态</th>
            <th style="width: 230px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in orders" :key="o.id">
            <td class="mono muted">#{{ o.id }}</td>
            <td>{{ resourceMap[o.resource_id]?.name || `资源 ${o.resource_id}` }}</td>
            <td class="mono" style="font-size: 12px">
              {{ fmtTime(o.start_time) }} → {{ fmtTime(o.end_time) }}
            </td>
            <td class="mono" style="color: var(--accent-orange)">
              {{ o.total_price != null ? `¥${o.total_price}` : '-' }}
            </td>
            <td>
              <span class="tag" :class="statusTag[o.status] || 'tag-blue'">
                {{ statusLabels[o.status] || o.status }}
              </span>
            </td>
            <td>
              <template v-if="busyId === o.id">
                <span class="muted" style="font-size: 12px">处理中…</span>
              </template>
              <template v-else>
                <button
                  v-if="o.status === 'pending' && isSupplierOf(o)"
                  class="btn btn-sm"
                  @click="changeStatus(o, 'confirmed')"
                >
                  确认接单
                </button>
                <button
                  v-if="o.status === 'confirmed' && isSupplierOf(o)"
                  class="btn btn-sm"
                  @click="changeStatus(o, 'ongoing')"
                >
                  开始服务
                </button>
                <button
                  v-if="o.status === 'ongoing' && isSupplierOf(o)"
                  class="btn btn-sm"
                  @click="changeStatus(o, 'finished', '确认完成该订单并结算佣金？')"
                >
                  完成
                </button>
                <button
                  v-if="(o.status === 'pending' || o.status === 'confirmed') && isDemanderOf(o)"
                  class="btn btn-danger btn-sm"
                  @click="changeStatus(o, 'cancelled', '确认取消该订单？')"
                >
                  取消
                </button>
                <button
                  v-if="o.status === 'finished'"
                  class="btn btn-ghost btn-sm"
                  @click="openReview(o)"
                >
                  评价
                </button>
                <button class="btn btn-ghost btn-sm" @click="openBilling(o)">账单</button>
                <span
                  v-if="!isSupplierOf(o) && !isDemanderOf(o)"
                  class="muted"
                  style="font-size: 12px"
                >-</span>
              </template>
            </td>
          </tr>
          <tr v-if="!orders.length">
            <td colspan="6">
              <div class="empty">{{ loading ? '加载中…' : '暂无订单，去「资源市场」预约一个吧' }}</div>
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

    <AppModal v-if="billing" :title="`订单 #${billing.id} 账单明细`" @close="billing = null">
      <div class="bill-head">
        <span class="bill-resource">
          {{ resourceMap[billing.resource_id]?.name || `资源 ${billing.resource_id}` }}
        </span>
        <span class="tag" :class="statusTag[billing.status] || 'tag-blue'">
          {{ statusLabels[billing.status] || billing.status }}
        </span>
      </div>

      <div class="bill-rows">
        <div class="bill-row">
          <span class="muted">预约时段</span>
          <span class="mono">{{ fmtTime(billing.start_time) }} → {{ fmtTime(billing.end_time) }}</span>
        </div>
        <div class="bill-row">
          <span class="muted">计费天数</span>
          <span class="mono">{{ billingDays || '-' }} 天（按天向上取整）</span>
        </div>
        <div class="bill-row">
          <span class="muted">资源单价</span>
          <span class="mono">
            {{
              resourceMap[billing.resource_id]?.price != null
                ? `${money(resourceMap[billing.resource_id].price)} / ${resourceMap[billing.resource_id].price_unit || '天'}`
                : '-'
            }}
          </span>
        </div>
        <div class="bill-row bill-total">
          <span class="muted">订单总价</span>
          <span class="mono">{{ money(billing.total_price) }}</span>
        </div>
        <div class="bill-row">
          <span class="muted">平台佣金率</span>
          <span class="mono">{{ billingCommissionRate }}</span>
        </div>
        <div class="bill-row">
          <span class="muted">平台佣金</span>
          <span class="mono">
            {{ billing.commission != null ? money(billing.commission) : '待结算（订单完成后结算）' }}
          </span>
        </div>
        <div class="bill-row">
          <span class="muted">供给方实收</span>
          <span class="mono">
            {{
              billing.commission != null && billing.total_price != null
                ? money(Number(billing.total_price) - Number(billing.commission))
                : '待结算'
            }}
          </span>
        </div>
        <div class="bill-row">
          <span class="muted">下单时间</span>
          <span class="mono">{{ fmtTime(billing.created_at) }}</span>
        </div>
        <div class="bill-row">
          <span class="muted">供给方 / 需求方</span>
          <span class="mono">#{{ billing.supplier_id }} / #{{ billing.demander_id }}</span>
        </div>
      </div>

      <template #footer>
        <button class="btn btn-ghost" @click="billing = null">关闭</button>
      </template>
    </AppModal>

    <AppModal v-if="reviewing" :title="`订单 #${reviewing.id} 评价`" @close="reviewing = null">
      <div v-if="reviewLoading" class="empty">加载中…</div>
      <template v-else>
        <div v-if="otherReview" class="existing">
          <div class="existing-head">
            对方评价
            <span class="stars">{{ '★'.repeat(otherReview.rating) }}{{ '☆'.repeat(5 - otherReview.rating) }}</span>
          </div>
          <div class="existing-body">{{ otherReview.content || '（无文字评价）' }}</div>
        </div>

        <div v-if="myReview" class="existing mine">
          <div class="existing-head">
            我的评价
            <span class="stars">{{ '★'.repeat(myReview.rating) }}{{ '☆'.repeat(5 - myReview.rating) }}</span>
          </div>
          <div class="existing-body">{{ myReview.content || '（无文字评价）' }}</div>
        </div>

        <template v-else>
          <div class="field">
            <label class="field-label">评分</label>
            <div class="stars-input">
              <button
                v-for="n in 5"
                :key="n"
                type="button"
                class="star"
                :class="{ on: n <= rating }"
                @click="rating = n"
              >★</button>
              <span class="muted" style="margin-left: 8px; font-size: 12px">{{ rating }} 分</span>
            </div>
          </div>
          <div class="field">
            <label class="field-label">评价内容（选填）</label>
            <textarea v-model="content" class="textarea" placeholder="说说这次服务的体验" />
          </div>
          <div class="error-text">{{ reviewError }}</div>
        </template>
      </template>

      <template #footer>
        <button class="btn btn-ghost" @click="reviewing = null">关闭</button>
        <button
          v-if="!myReview && !reviewLoading"
          class="btn"
          :disabled="submittingReview"
          @click="submitReview"
        >
          {{ submittingReview ? '提交中…' : '提交评价' }}
        </button>
      </template>
    </AppModal>
  </div>
</template>

<style scoped>
/* 账单明细 */
.bill-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-glow);
  margin-bottom: 10px;
}
.bill-resource { font-size: 14px; font-weight: 600; }
.bill-rows { display: flex; flex-direction: column; }
.bill-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 7px 0;
  font-size: 13px;
  border-bottom: 1px dashed rgba(64, 158, 255, 0.12);
}
.bill-row .mono { font-family: 'Consolas', 'Monaco', monospace; }
.bill-total .mono { color: var(--accent-orange); font-size: 15px; font-weight: 600; }

.existing {
  background: rgba(64, 158, 255, 0.06);
  border: 1px solid var(--border-glow);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.existing.mine { background: rgba(0, 255, 136, 0.05); border-color: rgba(0, 255, 136, 0.3); }
.existing-head {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.existing-body { font-size: 13px; color: var(--text-primary); }
.stars { color: var(--accent-orange); letter-spacing: 2px; }
.stars-input { display: flex; align-items: center; }
.star {
  background: none;
  border: none;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  color: rgba(240, 245, 255, 0.2);
  padding: 0 2px;
  transition: color 0.15s, transform 0.15s;
}
.star.on { color: var(--accent-orange); }
.star:hover { transform: scale(1.15); }
</style>
