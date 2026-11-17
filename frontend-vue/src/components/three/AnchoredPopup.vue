<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import * as THREE from 'three'
import type { ResourceItem, DeviceTelemetry } from '@/core/ColdStorageScene'
import { RESOURCE_STATUS_LABEL, RESOURCE_TYPE_LABEL } from '@/utils/labels'

const props = defineProps<{
  camera: THREE.Camera | null
  worldPos: THREE.Vector3 | null
  resource: ResourceItem | null
  telemetry: DeviceTelemetry | null
}>()

const screenX = ref(0)
const screenY = ref(0)
const visible = ref(false)
let rafId = 0

// 将世界坐标投影到屏幕坐标
function updatePosition() {
  if (!props.camera || !props.worldPos) {
    visible.value = false
    return
  }
  const v = props.worldPos.clone().project(props.camera)
  // v.x/y 范围 [-1, 1]，转为像素
  const canvas = document.querySelector('.scene-canvas') as HTMLCanvasElement | null
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  screenX.value = (v.x * 0.5 + 0.5) * rect.width
  screenY.value = (-v.y * 0.5 + 0.5) * rect.height
  // 背面不显示
  visible.value = v.z < 1
  rafId = requestAnimationFrame(updatePosition)
}

watch(
  () => [props.worldPos, props.camera],
  () => {
    cancelAnimationFrame(rafId)
    if (props.worldPos && props.camera) {
      updatePosition()
    } else {
      visible.value = false
    }
  },
  { immediate: true },
)

onUnmounted(() => cancelAnimationFrame(rafId))

const statusLabel = RESOURCE_STATUS_LABEL
const statusClass: Record<string, string> = {
  available: 'ok', booked: 'booked', pending: 'pending', offline: 'offline',
}
</script>

<template>
  <div
    v-if="visible && resource"
    class="anchored-popup"
    :style="{ left: screenX + 'px', top: screenY + 'px' }"
  >
    <div class="popup-header">
      <span class="popup-name">{{ resource.name }}</span>
      <span class="tag" :class="statusClass[resource.status] || 'pending'">
        {{ statusLabel[resource.status] || resource.status }}
      </span>
    </div>
    <div class="popup-body">
      <div class="row"><span class="k">类型</span><span class="v">{{ RESOURCE_TYPE_LABEL[resource.type] || resource.type }}</span></div>
      <div v-if="resource.location" class="row"><span class="k">位置</span><span class="v">{{ resource.location }}</span></div>
      <div v-if="resource.price != null" class="row">
        <span class="k">价格</span><span class="v price">¥{{ resource.price }}/天</span>
      </div>
      <template v-if="telemetry">
        <div class="divider"></div>
        <div class="row"><span class="k">温度</span><span class="v">{{ telemetry.temperature ?? '--' }}℃</span></div>
        <div class="row"><span class="k">湿度</span><span class="v">{{ telemetry.humidity ?? '--' }}%</span></div>
        <div v-if="telemetry.recorded_at" class="row">
          <span class="k">更新</span><span class="v time">{{ telemetry.recorded_at.slice(11, 19) }}</span>
        </div>
      </template>
      <template v-else>
        <div class="divider"></div>
        <div class="row"><span class="k">设备</span><span class="v muted">暂无实时数据</span></div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.anchored-popup {
  position: absolute;
  transform: translate(-50%, -110%);
  min-width: 200px;
  background: var(--bg-card);
  border: 1px solid var(--accent-cyan);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-glow);
  pointer-events: auto;
  z-index: 10;
  font-size: var(--fs-sm);
  color: var(--text-primary);
  backdrop-filter: blur(10px);
}
.popup-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-soft);
}
.popup-name { font-weight: 600; color: var(--accent-cyan); }
.tag {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: var(--fs-xs);
}
.tag.ok { background: rgba(0, 229, 255, 0.14); color: var(--status-available); }
.tag.booked { background: rgba(124, 108, 255, 0.16); color: var(--status-booked); }
.tag.pending { background: rgba(143, 163, 184, 0.14); color: var(--status-pending); }
.tag.offline { background: rgba(74, 90, 106, 0.2); color: var(--status-offline); }
.popup-body { padding: 10px 12px; }
.row {
  display: flex;
  justify-content: space-between;
  padding: 3px 0;
}
.k { color: var(--text-muted); }
.v { color: var(--text-primary); }
.v.price { color: var(--accent-orange); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.v.time { font-family: var(--font-mono); font-size: var(--fs-xs); font-variant-numeric: tabular-nums; }
.v.muted { color: var(--text-muted); }
.divider {
  height: 1px;
  background: var(--border-soft);
  margin: 6px 0;
}
</style>
