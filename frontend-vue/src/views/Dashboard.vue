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
import TwinStage from '@/components/twin/TwinStage.vue'
import { useResourcesStore } from '@/stores/resources'
import { useIoTStore } from '@/stores/iot'
import { useMatchStore } from '@/stores/match'
import { useOrdersStore } from '@/stores/orders'
import { useTwinStore } from '@/stores/twin'
import { useScreenScale } from '@/composables/useScreenScale'
import { realtime } from '@/ws/realtime'

const resourcesStore = useResourcesStore()
const iotStore = useIoTStore()
const matchStore = useMatchStore()
const ordersStore = useOrdersStore()
const twinStore = useTwinStore()

// 1920×1080 设计基准等比缩放（2K/4K 大屏自动放大，小窗口回退流式布局）
const { scale, scaled } = useScreenScale()

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
    twinStore.fetchSnapshot().catch(() => {}),
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
  // 窄表遥测直达孪生舞台：点位值、设备状态、节点汇总即时刷新
  realtime.on('telemetry', (d) => twinStore.onTelemetry(d))
  realtime.on('twin_event', (d) => twinStore.onTwinEvent(d))

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
  <div class="screen-viewport">
    <div
      class="screen-stage"
      :class="{ 'is-scaled': scaled }"
      :style="scaled ? { '--screen-scale': String(scale) } : undefined"
    >
      <div class="dashboard">
        <!-- 顶部标题栏 -->
        <Header />

        <!-- 主体三栏布局 -->
        <main class="main-grid">
          <!-- 左栏：指标 + 资源 + 撮合 -->
          <aside class="col col-left">
            <StatCards class="mb-12" />
            <ResourceList class="mb-12" />
            <MatchPanel />
          </aside>

          <!-- 中央：数字孪生四级下钻（未配置节点时回落到三维冷链基地） -->
          <section class="col col-center">
            <TwinStage v-if="twinStore.hasTree" />
            <ColdStorageScene v-else ref="sceneRef" />
          </section>

          <!-- 右栏：IoT + 告警 + 订单 -->
          <aside class="col col-right">
            <IoTRealtime class="mb-12 iot-fixed" />
            <AlertList class="mb-12" />
            <OrderPanel />
          </aside>
        </main>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 视口：深色底做黑边，缩放后多出来的区域不着色 */
.screen-viewport {
  position: relative;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-deep);
}

/* 未缩放（小窗口 / 手机）：走流式布局 */
.screen-stage {
  width: 100%;
  height: 100%;
}

/* 1920×1080 固定画布，整体等比缩放，居中留黑边 */
.screen-stage.is-scaled {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 1920px;
  height: 1080px;
  transform: translate(-50%, -50%) scale(var(--screen-scale, 1));
  transform-origin: center center;
}

.dashboard {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-rows: 60px 1fr;
  background: var(--bg-primary);
}

.main-grid {
  display: grid;
  grid-template-columns: 340px 1fr 380px;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4) var(--space-4);
  overflow: hidden;
  min-height: 0;
}

.col {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

/* 面板入场：自上而下 stagger，总时长控制在 400ms 内 */
.col > * {
  animation: panel-in 0.42s cubic-bezier(0.22, 0.8, 0.3, 1) both;
}
.col > *:nth-child(1) { animation-delay: 0ms; }
.col > *:nth-child(2) { animation-delay: 90ms; }
.col > *:nth-child(3) { animation-delay: 180ms; }

@keyframes panel-in {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: none; }
}

/* 中央舞台为一级视觉：强边框 + 外发光 */
.col-center {
  position: relative;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-panel);
  overflow: hidden;
  min-height: 0;
}

.mb-12 { margin-bottom: var(--space-3); }

/* 折线图面板固定高度，把剩余空间让给告警/订单列表 */
.iot-fixed { flex: 0 0 236px; }

/* ===== 移动端 / 窄窗口：单列堆叠，允许页面滚动 ===== */
@media (max-width: 1024px) {
  .dashboard { height: auto; min-height: 100vh; grid-template-rows: auto 1fr; }
  .main-grid {
    grid-template-columns: 1fr;
    overflow: visible;
    padding: 10px;
  }
  .col { overflow: visible; }
  .col-center { min-height: 380px; }
  .iot-fixed { flex: none; }
}
</style>
