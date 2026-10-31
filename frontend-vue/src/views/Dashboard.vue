<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import Header from '@/components/dashboard/Header.vue'
import StatCards from '@/components/dashboard/StatCards.vue'
import ResourceList from '@/components/dashboard/ResourceList.vue'
import MatchPanel from '@/components/dashboard/MatchPanel.vue'
import IoTRealtime from '@/components/dashboard/IoTRealtime.vue'
import AlertList from '@/components/dashboard/AlertList.vue'
import OrderPanel from '@/components/dashboard/OrderPanel.vue'
import ColdStorageScene from '@/components/three/ColdStorageScene.vue'
import { useResourcesStore } from '@/stores/resources'
import { useIoTStore } from '@/stores/iot'
import { useMatchStore } from '@/stores/match'
import { useOrdersStore } from '@/stores/orders'
import { realtime } from '@/ws/realtime'

const resourcesStore = useResourcesStore()
const iotStore = useIoTStore()
const matchStore = useMatchStore()
const ordersStore = useOrdersStore()

// 三维冷链场景实例，资源状态变化时驱动冷链箱颜色刷新
const sceneRef = ref<InstanceType<typeof ColdStorageScene> | null>(null)

// 监听资源列表变化（整体 fetch 替换 / WS 局部 upsert 都触发），刷新冷链箱颜色
watch(
  () => resourcesStore.items,
  () => sceneRef.value?.handleResourcesChange(),
  { deep: true },
)

// 数据刷新定时器
let refreshTimer: number | null = null

onMounted(async () => {
  // 1) 首次数据拉取（并行，orders 需要 token 才请求）
  const token = localStorage.getItem('hlg_token')
  await Promise.all([
    resourcesStore.fetch().catch(() => {}),
    iotStore.fetchLatest().catch(() => {}),
    iotStore.fetchAlerts().catch(() => {}),
    matchStore.fetch({ top_n: 5 }).catch(() => {}),
    token ? ordersStore.fetch().catch(() => {}) : Promise.resolve(),
  ])

  // 2) WebSocket 连接 + 订阅
  realtime.connect()
  realtime.on('iot_data', (d) => iotStore.onRealtime(d))
  realtime.on('order_created', () => ordersStore.fetch())
  realtime.on('order_status_changed', (d) => ordersStore.onRealtime(d))
  // 资源状态变更（下单 booked / 取消完成 available）→ 立即刷新，驱动冷链箱颜色实时变化
  realtime.on('resource_updated', () => resourcesStore.fetch())
  // 告警被运营端处理 → 立刻从活跃告警列表移除
  realtime.on('alert_resolved', (d) => iotStore.onAlertResolved(d.alert_id))

  // 3) 定时刷新（30s）
  refreshTimer = window.setInterval(() => {
    resourcesStore.fetch()
    matchStore.fetch({ top_n: 5 })
    iotStore.fetchAlerts()
  }, 30000) as unknown as number
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  realtime.close()
})
</script>

<template>
  <div class="dashboard">
    <!-- 顶部标题栏 -->
    <Header />

    <!-- 主体三栏布局 -->
    <main class="main-grid">
      <!-- 左栏：统计 + 资源 + 撮合 -->
      <aside class="col col-left">
        <StatCards class="mb-12" />
        <ResourceList class="mb-12" />
        <MatchPanel />
      </aside>

      <!-- 中央：三维冷链基地 -->
      <section class="col col-center">
        <ColdStorageScene ref="sceneRef" />
      </section>

      <!-- 右栏：IoT + 告警 + 订单 -->
      <aside class="col col-right">
        <IoTRealtime class="mb-12" />
        <AlertList class="mb-12" />
        <OrderPanel />
      </aside>
    </main>
  </div>
</template>

<style scoped>
.dashboard {
  width: 100vw;
  height: 100vh;
  display: grid;
  grid-template-rows: 60px 1fr;
  background: var(--bg-primary);
}

.main-grid {
  display: grid;
  grid-template-columns: 340px 1fr 340px;
  gap: 16px;
  padding: 12px 16px 16px;
  overflow: hidden;
}

.col {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.col-center {
  position: relative;
  border: 1px solid var(--border-glow);
  border-radius: 8px;
  background: var(--bg-card);
  overflow: hidden;
}

.mb-12 { margin-bottom: 12px; }

/* ===== 移动端：单列堆叠，允许页面滚动 ===== */
@media (max-width: 1024px) {
  .dashboard { height: auto; min-height: 100vh; grid-template-rows: auto 1fr; }
  .main-grid {
    grid-template-columns: 1fr;
    overflow: visible;
    padding: 10px;
  }
  .col { overflow: visible; }
  .col-center { min-height: 380px; }
}
</style>
