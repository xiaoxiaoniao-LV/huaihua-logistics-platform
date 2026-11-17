<script setup lang="ts">
import { computed, ref } from 'vue'
import { onPullDownRefresh, onShow } from '@dcloudio/uni-app'
import { cancelOrder, listMyOrders, orderStatusLabels, orderStatusTags, type Order } from '@/api/orders'
import { getResource } from '@/api/resources'
import { isLoggedIn } from '@/api/http'

const orders = ref<Order[]>([])
const names = ref<Record<number, string>>({})
const loading = ref(false)
const loaded = ref(false)
const activeFilter = ref('all')
const loggedIn = ref(isLoggedIn())

const filters = [
  { value: 'all', label: '全部' },
  { value: 'pending', label: '待确认' },
  { value: 'doing', label: '进行中' },
  { value: 'done', label: '已完成' },
  { value: 'closed', label: '已关闭' },
]

const visible = computed(() => {
  const f = activeFilter.value
  if (f === 'all') return orders.value
  if (f === 'pending') return orders.value.filter((o) => o.status === 'pending')
  if (f === 'doing') return orders.value.filter((o) => o.status === 'confirmed' || o.status === 'ongoing')
  if (f === 'done') return orders.value.filter((o) => o.status === 'finished' || o.status === 'settled')
  return orders.value.filter((o) => ['rejected', 'cancelled', 'expired'].includes(o.status))
})

function fmt(v: string) {
  return v ? v.replace('T', ' ').slice(0, 16) : '—'
}

async function loadNames(rows: Order[]) {
  const ids = [...new Set(rows.map((o) => o.resource_id))]
  const map: Record<number, string> = {}
  await Promise.all(
    ids.map(async (id) => {
      try {
        const r = await getResource(id, true)
        map[id] = r.name
      } catch (e) {
        map[id] = `资源 #${id}`
      }
    }),
  )
  names.value = map
}

async function load() {
  loggedIn.value = isLoggedIn()
  if (!loggedIn.value) {
    orders.value = []
    loaded.value = true
    return
  }
  loading.value = true
  try {
    const rows = await listMyOrders()
    orders.value = rows
    loaded.value = true
    await loadNames(rows)
  } catch (e) {
    // request 已提示
  } finally {
    loading.value = false
  }
}

function goLogin() {
  uni.switchTab({ url: '/pages/mine/mine' })
}

function goDetail(id: number) {
  uni.navigateTo({ url: `/pages/detail/detail?id=${id}` })
}

function askCancel(order: Order) {
  uni.showModal({
    title: '取消预约',
    content: `确认取消订单 #${order.id}？取消后不可恢复。`,
    confirmColor: '#bf2c2c',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await cancelOrder(order.id)
        uni.showToast({ title: '已取消', icon: 'none' })
        await load()
      } catch (e) {
        // request 已提示
      }
    },
  })
}

onShow(() => load())

onPullDownRefresh(async () => {
  await load()
  uni.stopPullDownRefresh()
})
</script>

<template>
  <view class="page">
    <view v-if="!loggedIn" class="card guest">
      <view class="guest-title">登录后查看你的预约</view>
      <view class="small muted">游客可以浏览与撮合，下单需要需求方账号</view>
      <button class="btn guest-btn" @tap="goLogin">去登录 / 注册</button>
    </view>

    <template v-else>
      <scroll-view scroll-x class="chips">
        <view
          v-for="f in filters"
          :key="f.value"
          class="chip"
          :class="{ 'chip-on': activeFilter === f.value }"
          @tap="activeFilter = f.value"
        >
          {{ f.label }}
        </view>
      </scroll-view>

      <view v-for="o in visible" :key="o.id" class="card">
        <view class="between">
          <text class="order-id mono">#{{ o.id }}</text>
          <text class="tag" :class="orderStatusTags[o.status] || 'tag-grey'">
            {{ orderStatusLabels[o.status] || o.status }}
          </text>
        </view>
        <view class="res-name" @tap="goDetail(o.resource_id)">
          {{ names[o.resource_id] || `资源 #${o.resource_id}` }}
        </view>
        <view class="small muted line">时段：{{ fmt(o.start_time) }} ~ {{ fmt(o.end_time) }}</view>
        <view class="small muted line">下单：{{ fmt(o.created_at) }}</view>
        <view class="between foot">
          <view>
            <text class="price">¥{{ o.total_price }}</text>
            <text class="small muted"> · {{ o.payment_status === 'paid' ? '已支付' : '未支付' }}</text>
          </view>
          <view v-if="o.status === 'pending'" class="cancel" @tap="askCancel(o)">取消预约</view>
        </view>
      </view>

      <view v-if="loaded && !visible.length" class="empty">
        {{ orders.length ? '该分类下暂无订单' : '还没有预约，去「找资源」看看吧' }}
      </view>
      <view v-if="loading" class="empty">加载中…</view>
    </template>
  </view>
</template>

<style scoped>
.guest { text-align: center; padding: 60rpx 40rpx; }
.guest-title { font-size: 32rpx; font-weight: 700; margin-bottom: 14rpx; }
.guest-btn { margin-top: 36rpx; }
.chips { white-space: nowrap; padding: 20rpx 24rpx 0; }
.chip {
  display: inline-block;
  padding: 12rpx 28rpx;
  margin-right: 16rpx;
  border-radius: 999rpx;
  background: #fff;
  color: #4a6076;
  font-size: 26rpx;
  border: 1rpx solid #e2eaf2;
}
.chip-on { background: #0a8f96; border-color: #0a8f96; color: #fff; font-weight: 600; }
.order-id { font-size: 26rpx; color: #7d8fa3; }
.res-name { font-size: 30rpx; font-weight: 600; margin: 16rpx 0 10rpx; }
.line { margin-top: 6rpx; }
.foot { margin-top: 18rpx; padding-top: 18rpx; border-top: 1rpx solid #eef2f7; }
.cancel {
  font-size: 26rpx;
  color: #bf2c2c;
  border: 1rpx solid #f3c9c9;
  border-radius: 999rpx;
  padding: 10rpx 28rpx;
}
</style>
