<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { formatPrice, getResource, typeLabels, type Resource } from '@/api/resources'
import { createOrder } from '@/api/orders'
import { isLoggedIn } from '@/api/http'

const resource = ref<Resource | null>(null)
const startDate = ref('')
const endDate = ref('')
const submitting = ref(false)

function isoDate(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const days = computed(() => {
  if (!startDate.value || !endDate.value) return 0
  const s = new Date(`${startDate.value}T00:00:00`).getTime()
  const e = new Date(`${endDate.value}T00:00:00`).getTime()
  if (e <= s) return 0
  return Math.ceil((e - s) / 86400000)
})

const estimate = computed(() => {
  const p = Number(resource.value?.price || 0)
  if (!days.value || !p) return '—'
  return `¥${(p * days.value).toFixed(2)}`
})

const windowText = computed(() => {
  const r = resource.value
  if (!r?.available_start && !r?.available_end) return '可随时预约'
  const s = r?.available_start ? r.available_start.slice(0, 10) : '即约'
  const e = r?.available_end ? r.available_end.slice(0, 10) : '长期'
  return `${s} ~ ${e}`
})

async function load(id: number) {
  try {
    const r = await getResource(id)
    resource.value = r
    const today = new Date()
    const start = r.available_start ? new Date(r.available_start) : today
    const base = start.getTime() > today.getTime() ? start : today
    const end = r.available_end ? new Date(r.available_end) : new Date(base.getTime() + 86400000)
    if (end.getTime() <= base.getTime()) end.setTime(base.getTime() + 86400000)
    startDate.value = isoDate(base)
    endDate.value = isoDate(end)
  } catch (e) {
    // request 已提示
  }
}

function onStartChange(e: { detail: { value: string } }) {
  startDate.value = e.detail.value
  if (endDate.value <= startDate.value) {
    const d = new Date(`${startDate.value}T00:00:00`)
    d.setDate(d.getDate() + 1)
    endDate.value = isoDate(d)
  }
}

function onEndChange(e: { detail: { value: string } }) {
  endDate.value = e.detail.value
}

async function submit() {
  if (!resource.value) return
  if (!isLoggedIn()) {
    uni.showModal({
      title: '请先登录',
      content: '下单需要登录需求方账号，是否前往「我的」登录？',
      confirmText: '去登录',
      success: (res) => {
        if (res.confirm) uni.switchTab({ url: '/pages/mine/mine' })
      },
    })
    return
  }
  if (!days.value) {
    uni.showToast({ title: '请选择有效的用车/用仓时段', icon: 'none' })
    return
  }
  submitting.value = true
  try {
    await createOrder({
      resource_id: resource.value.id,
      start_time: `${startDate.value}T00:00:00`,
      end_time: `${endDate.value}T00:00:00`,
    })
    uni.showToast({ title: '预约提交成功', icon: 'success' })
    setTimeout(() => uni.switchTab({ url: '/pages/orders/orders' }), 900)
  } catch (e) {
    // request 已提示（含时段冲突）
  } finally {
    submitting.value = false
  }
}

onLoad((options) => {
  const id = Number(options?.id)
  if (id) load(id)
  else uni.showToast({ title: '缺少资源编号', icon: 'none' })
})
</script>

<template>
  <view class="page">
    <view v-if="resource" class="card">
      <view class="between">
        <text class="title">{{ resource.name }}</text>
        <text class="tag tag-green">可预约</text>
      </view>
      <view class="small muted meta">
        {{ typeLabels[resource.type] || resource.type }} · {{ resource.location || '位置待定' }}
      </view>
      <view class="price-line">
        <text class="price big">{{ formatPrice(resource.price, resource.price_unit) }}</text>
      </view>
      <view v-if="resource.description" class="desc">{{ resource.description }}</view>
      <view class="divider" />
      <view class="kv">
        <text class="muted">可租窗口</text>
        <text>{{ windowText }}</text>
      </view>
      <view class="kv">
        <text class="muted">资源编号</text>
        <text class="mono">#{{ resource.id }}</text>
      </view>
    </view>

    <view class="card">
      <view class="section-title">选择时段</view>
      <view class="picker-row">
        <text class="muted">开始</text>
        <picker mode="date" :value="startDate" @change="onStartChange">
          <view class="picker-value">{{ startDate || '请选择' }}</view>
        </picker>
      </view>
      <view class="picker-row">
        <text class="muted">结束</text>
        <picker mode="date" :value="endDate" :start="startDate" @change="onEndChange">
          <view class="picker-value">{{ endDate || '请选择' }}</view>
        </picker>
      </view>
      <view class="divider" />
      <view class="between">
        <text class="muted">预计费用（{{ days }} 天）</text>
        <text class="price big">{{ estimate }}</text>
      </view>
      <view class="small muted tip">按天计费，最终以供给方确认与线下合同为准</view>
    </view>

    <view class="footer">
      <button class="btn" :disabled="submitting" @tap="submit">
        {{ submitting ? '提交中…' : '提交预约需求' }}
      </button>
      <view class="small muted foot-tip">虚拟构建 · 演示环境，不产生真实交易</view>
    </view>
  </view>
</template>

<style scoped>
.title { font-size: 34rpx; font-weight: 700; flex: 1; margin-right: 16rpx; }
.meta { margin-top: 10rpx; }
.price-line { margin-top: 20rpx; display: flex; align-items: baseline; }
.big { font-size: 40rpx; }
.desc { margin-top: 16rpx; color: #4a6076; font-size: 26rpx; line-height: 1.7; }
.divider { height: 1rpx; background: #eef2f7; margin: 22rpx 0; }
.kv { display: flex; justify-content: space-between; font-size: 26rpx; padding: 8rpx 0; }
.section-title { font-size: 30rpx; font-weight: 700; margin-bottom: 10rpx; }
.picker-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18rpx 0;
  font-size: 28rpx;
}
.picker-value {
  background: #f2f6fb;
  border-radius: 12rpx;
  padding: 14rpx 28rpx;
  font-size: 28rpx;
  color: #0b2a4a;
}
.tip { margin-top: 14rpx; }
.footer { padding: 12rpx 24rpx 40rpx; }
.foot-tip { text-align: center; margin-top: 16rpx; }
</style>
