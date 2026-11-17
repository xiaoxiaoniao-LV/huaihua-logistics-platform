<script setup lang="ts">
import { ref } from 'vue'
import { onLoad, onPullDownRefresh } from '@dcloudio/uni-app'
import {
  formatPrice,
  listResources,
  recommendResources,
  typeLabels,
  type MatchItem,
  type Resource,
} from '@/api/resources'

const types = [
  { value: '', label: '全部' },
  { value: 'warehouse', label: '冷库' },
  { value: 'cold_box', label: '冷链箱位' },
  { value: 'vehicle', label: '冷藏运输' },
  { value: 'equipment', label: '温控设备' },
]

const keyword = ref('')
const activeType = ref('')
const list = ref<Resource[]>([])
const matches = ref<MatchItem[]>([])
const loading = ref(false)
const loaded = ref(false)

async function loadAll() {
  loading.value = true
  try {
    const [rows, rec] = await Promise.all([
      listResources({
        keyword: keyword.value.trim() || undefined,
        type: activeType.value || undefined,
        page_size: 50,
      }),
      recommendResources({ type: activeType.value || undefined, top_n: 3 }),
    ])
    list.value = rows
    matches.value = rec.results || []
    loaded.value = true
  } catch (e) {
    // request 已统一提示
  } finally {
    loading.value = false
  }
}

function pickType(value: string) {
  if (activeType.value === value) return
  activeType.value = value
  loadAll()
}

function goDetail(id: number) {
  uni.navigateTo({ url: `/pages/detail/detail?id=${id}` })
}

function priceText(item: Resource | MatchItem) {
  return formatPrice(item.price, item.price_unit)
}

onLoad(() => loadAll())

onPullDownRefresh(async () => {
  await loadAll()
  uni.stopPullDownRefresh()
})
</script>

<template>
  <view class="page">
    <view class="hero">
      <view class="hero-title">怀化国际陆港 · 冷链资源</view>
      <view class="hero-sub">虚拟构建 · 游客可直接浏览，登录后下单</view>
      <view class="search">
        <input
          v-model="keyword"
          class="search-input"
          placeholder="搜索冷库、箱位、冷藏车…"
          confirm-type="search"
          @confirm="loadAll"
        />
        <view class="search-btn" @tap="loadAll">搜索</view>
      </view>
    </view>

    <scroll-view scroll-x class="chips">
      <view
        v-for="t in types"
        :key="t.value"
        class="chip"
        :class="{ 'chip-on': activeType === t.value }"
        @tap="pickType(t.value)"
      >
        {{ t.label }}
      </view>
    </scroll-view>

    <view v-if="matches.length" class="card">
      <view class="between">
        <text class="section-title">智能撮合推荐</text>
        <text class="small muted">按价格 / 信用 / 窗口综合评分</text>
      </view>
      <view
        v-for="m in matches"
        :key="m.resource_id"
        class="match-item"
        @tap="goDetail(m.resource_id)"
      >
        <view class="match-rank">
          <text class="rank-score">{{ m.match_score }}</text>
          <text class="rank-label">分</text>
        </view>
        <view class="match-body">
          <view class="between">
            <text class="match-name">{{ m.name }}</text>
            <text class="small price">{{ priceText(m) }}</text>
          </view>
          <view class="small muted">{{ typeLabels[m.type] || m.type }} · {{ m.location || '位置待定' }}</view>
          <view v-if="m.reasons.length" class="reasons">
            <text v-for="(r, i) in m.reasons" :key="i" class="reason">{{ r }}</text>
          </view>
        </view>
      </view>
    </view>

    <view class="list-head">
      <text class="section-title">可预约资源</text>
      <text class="small muted">{{ list.length }} 条</text>
    </view>

    <view v-for="item in list" :key="item.id" class="card res-card" @tap="goDetail(item.id)">
      <view class="between">
        <text class="res-name">{{ item.name }}</text>
        <text class="tag tag-green">可预约</text>
      </view>
      <view class="small muted res-meta">
        {{ typeLabels[item.type] || item.type }} · {{ item.location || '位置待定' }}
      </view>
      <view v-if="item.description" class="small res-desc">{{ item.description }}</view>
      <view class="between res-foot">
        <text class="price">{{ priceText(item) }}</text>
        <text class="small muted">
          {{ item.available_start ? item.available_start.slice(0, 10) : '即约' }} 起
        </text>
      </view>
    </view>

    <view v-if="loaded && !list.length" class="empty">暂无符合条件的资源，换个类型试试</view>
    <view v-if="loading" class="empty">加载中…</view>
  </view>
</template>

<style scoped>
.hero {
  background: linear-gradient(150deg, #0b2a4a, #0a5b74 70%, #0a8f96);
  padding: 40rpx 24rpx 36rpx;
  color: #fff;
}
.hero-title { font-size: 38rpx; font-weight: 700; letter-spacing: 1rpx; }
.hero-sub { margin-top: 8rpx; font-size: 24rpx; opacity: 0.75; }
.search {
  margin-top: 24rpx;
  display: flex;
  align-items: center;
  background: #fff;
  border-radius: 999rpx;
  padding: 8rpx 8rpx 8rpx 28rpx;
}
.search-input { flex: 1; font-size: 26rpx; color: #0f2233; }
.search-btn {
  background: linear-gradient(135deg, #12b3b8, #0a7fa3);
  color: #fff;
  font-size: 26rpx;
  padding: 14rpx 32rpx;
  border-radius: 999rpx;
}
.chips { white-space: nowrap; padding: 20rpx 24rpx 0; background: #f2f6fb; }
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
.section-title { font-size: 30rpx; font-weight: 700; }
.match-item {
  display: flex;
  gap: 20rpx;
  padding: 22rpx 0;
  border-bottom: 1rpx solid #eef2f7;
}
.match-item:last-child { border-bottom: none; padding-bottom: 0; }
.match-rank {
  width: 88rpx;
  height: 88rpx;
  border-radius: 18rpx;
  background: #eaf7f8;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.rank-score { color: #0a8f96; font-size: 30rpx; font-weight: 700; }
.rank-label { font-size: 20rpx; color: #6fb3b7; }
.match-body { flex: 1; min-width: 0; }
.match-name { font-size: 28rpx; font-weight: 600; }
.reasons { margin-top: 8rpx; display: flex; flex-wrap: wrap; gap: 10rpx; }
.reason {
  font-size: 20rpx;
  color: #0a7fa3;
  background: #eef7fb;
  padding: 4rpx 14rpx;
  border-radius: 999rpx;
}
.list-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 26rpx 24rpx 0;
}
.res-card { padding: 26rpx 28rpx; }
.res-name { font-size: 30rpx; font-weight: 600; }
.res-meta { margin-top: 8rpx; }
.res-desc {
  margin-top: 10rpx;
  color: #4a6076;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.res-foot { margin-top: 16rpx; }
</style>
