<script setup lang="ts">
import { computed } from 'vue'
import { useResourcesStore } from '@/stores/resources'
import { useIoTStore } from '@/stores/iot'
import { useOrdersStore } from '@/stores/orders'

const resources = useResourcesStore()
const iot = useIoTStore()
const orders = useOrdersStore()

const stats = computed(() => [
  { label: '资源总数',   value: resources.items.length, color: 'cyan' },
  { label: '可用资源',   value: resources.available.length, color: 'green' },
  { label: '活跃设备',   value: iot.latestList.length, color: 'blue' },
  { label: '订单总数',   value: orders.items.length, color: 'orange' },
])
</script>

<template>
  <div class="panel">
    <div class="panel-title">核心指标</div>
    <div class="panel-body stat-grid">
      <div v-for="s in stats" :key="s.label" class="stat-card">
        <div class="stat-value" :class="`stat-${s.color}`">{{ s.value }}</div>
        <div class="stat-label">{{ s.label }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.stat-card {
  text-align: center;
  padding: 10px 4px;
  border: 1px solid var(--border-glow);
  border-radius: 6px;
  background: rgba(0, 229, 255, 0.04);
}
.stat-cyan  { color: var(--accent-cyan); font-family: 'Consolas', monospace; font-size: 22px; font-weight: 700; }
.stat-green { color: var(--accent-green); font-family: 'Consolas', monospace; font-size: 22px; font-weight: 700; }
.stat-blue  { color: var(--accent); font-family: 'Consolas', monospace; font-size: 22px; font-weight: 700; }
.stat-orange{ color: var(--accent-orange); font-family: 'Consolas', monospace; font-size: 22px; font-weight: 700; }
.stat-label { font-size: 11px; color: var(--text-secondary); margin-top: 4px; }
</style>
