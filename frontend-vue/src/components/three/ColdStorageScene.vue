<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { ColdStorageScene, type PickResult, type ResourceItem } from '@/core/ColdStorageScene'
import { useResourcesStore } from '@/stores/resources'
import { useIoTStore } from '@/stores/iot'
import AnchoredPopup from './AnchoredPopup.vue'

const resources = useResourcesStore()
const iot = useIoTStore()

const canvasRef = ref<HTMLCanvasElement | null>(null)
let scene: ColdStorageScene | null = null

// 拾取选中的对象（用于弹窗）
const picked = ref<PickResult | null>(null)
const pickedCamera = ref<THREE.Camera | null>(null)

// 弹窗展示的资源信息：优先用完整的资源对象（含位置/价格），设备节点用自身信息兜底
const popupResource = computed(() => {
  const p = picked.value
  if (!p) return null
  const full = resources.items.find((r) => r.id === p.resource_id)
  if (full) return full
  return {
    id: p.resource_id,
    name: p.name || p.device_code || '未命名',
    type: p.type,
    status: p.status,
  }
})

// 弹窗实时数据：优先取该资源绑定设备的最新值，设备节点则按自身 device_code 取
const popupTelemetry = computed(() => {
  const p = picked.value
  if (!p) return null
  const point =
    (p.resource_id ? iot.latestByResource[p.resource_id] : undefined) ||
    (p.device_code ? iot.latest[p.device_code] : undefined)
  if (!point) return null
  return {
    device_code: point.device_code,
    temperature: point.temperature,
    humidity: point.humidity,
    longitude: point.longitude,
    latitude: point.latitude,
    recorded_at: point.recorded_at,
  }
})

onMounted(() => {
  if (!canvasRef.value) return
  scene = new ColdStorageScene(canvasRef.value)
  scene.init()
  // 传入资源列表
  scene.setResources(resources.items as ResourceItem[])
  // 注册拾取回调
  scene.setPickCallback((result) => {
    picked.value = result
  })
  // 暴露相机给弹窗做投影
  pickedCamera.value = scene.camera
  // 把当前已有的 IoT 最新值推给场景（供 3D 内颜色/标签使用）
  scene.setTelemetry(Object.values(iot.latest))
})

// 资源变化时刷新冷链箱
watch(
  () => resources.items,
  (items) => {
    scene?.setResources(items as ResourceItem[])
  },
  { deep: true },
)

// IoT 实时数据变化时同步给场景
watch(
  () => iot.latest,
  (latest) => {
    scene?.setTelemetry(Object.values(latest))
  },
  { deep: true },
)

onUnmounted(() => {
  scene?.dispose()
  scene = null
})

// 导出给外部 watch 调用（保持与 Dashboard.vue 的契约）
function handleResourcesChange() {
  scene?.refreshColors()
}
defineExpose({ handleResourcesChange })
</script>

<template>
  <div class="scene-wrapper">
    <canvas ref="canvasRef" class="scene-canvas"></canvas>

    <AnchoredPopup
      :camera="pickedCamera"
      :world-pos="picked?.position || null"
      :resource="popupResource"
      :telemetry="popupTelemetry"
    />

    <div class="scene-hint">
      <div class="hint-title">冷链基地三维视图</div>
      <div class="hint-sub">拖拽旋转 · 滚轮缩放 · 点击冷链箱/设备查看数据</div>
    </div>
  </div>
</template>

<style scoped>
.scene-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
}
.scene-canvas {
  width: 100%;
  height: 100%;
  display: block;
}
.scene-hint {
  position: absolute;
  bottom: 12px;
  left: 16px;
  padding: 8px 14px;
  background: rgba(10, 26, 54, 0.8);
  border: 1px solid var(--border-glow);
  border-radius: 6px;
  font-size: 11px;
  color: var(--text-secondary);
}
.hint-title { font-weight: 600; color: var(--accent-cyan); font-size: 12px; margin-bottom: 2px; }
.hint-sub { font-size: 10px; color: var(--text-muted); }
</style>
