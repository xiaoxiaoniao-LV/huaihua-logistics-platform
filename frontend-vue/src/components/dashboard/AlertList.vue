<script setup lang="ts">
import { computed } from 'vue'
import { useIoTStore } from '@/stores/iot'
import { useTwinStore } from '@/stores/twin'
import type { IoTAlert } from '@/api/iot'
import { ALERT_LEVEL_CLASS, ALERT_LEVEL_LABEL } from '@/utils/labels'
import { useNewItemFlash } from '@/composables/useNewItemFlash'

const iot = useIoTStore()
const twin = useTwinStore()

const list = computed(() => iot.activeAlerts.slice(0, 8))
const flashing = useNewItemFlash(() => iot.activeAlerts.map((a) => a.id))

const levelText = (level: string) => ALERT_LEVEL_LABEL[level] || '提示'
const levelClass = (level: string) => ALERT_LEVEL_CLASS[level] || 'alert-info'

/** 点击告警 → 三维舞台定位到对应设备/货位 */
function locate(alert: IoTAlert) {
  if (alert.device_code) twin.focusDevice(alert.device_code)
  else if (alert.resource_id) twin.focusResource(alert.resource_id)
}
</script>

<template>
  <div class="panel panel--secondary panel--grow">
    <div class="panel-title">活跃告警</div>
    <div class="panel-body">
      <div v-if="!list.length" class="empty" style="color: var(--accent-green);">✓ 无活跃告警</div>
      <div v-else class="alert-list">
        <div
          v-for="a in list"
          :key="a.id"
          class="alert-item"
          :class="[levelClass(a.level), { 'is-new': flashing.has(String(a.id)) }]"
          title="点击在三维场景中定位"
          @click="locate(a)"
        >
          <span class="tag" :class="`tag-${a.level === 'critical' ? 'red' : a.level === 'warn' ? 'orange' : 'blue'}`">
            {{ levelText(a.level) }}
          </span>
          <span class="msg">{{ a.message }}</span>
          <span class="time">{{ a.created_at.slice(11, 16) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.alert-list { display: flex; flex-direction: column; gap: 6px; }
.alert-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px 8px;
  border-left: 3px solid transparent;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  font-size: var(--fs-xs);
  cursor: pointer;
  transition: background 0.2s;
}
.alert-item:hover { filter: brightness(1.18); }
/* 严重：红底 + 呼吸脉冲，是最需要被看见的一级 */
.alert-critical {
  background: rgba(255, 71, 87, 0.14);
  border-left-color: var(--alert-critical);
  animation: alert-breath 1.8s ease-in-out infinite;
}
/* 警告：琥珀左边框，不做整块红底 */
.alert-warn {
  background: rgba(255, 159, 67, 0.08);
  border-left-color: var(--alert-warn);
}
/* 提示：蓝左边框 */
.alert-info {
  background: rgba(64, 158, 255, 0.08);
  border-left-color: var(--alert-info);
}
@keyframes alert-breath {
  0%, 100% { background: rgba(255, 71, 87, 0.14); box-shadow: none; }
  50%      { background: rgba(255, 71, 87, 0.26); box-shadow: 0 0 12px rgba(255, 71, 87, 0.28); }
}
.msg { flex: 1; color: var(--text-primary); }
.time {
  font-family: var(--font-mono);
  color: var(--text-muted);
  font-size: var(--fs-xs);
  font-variant-numeric: tabular-nums;
}
.empty { text-align: center; padding: var(--space-4); font-size: var(--fs-sm); }
</style>
