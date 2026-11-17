<script setup lang="ts">
import { computed } from 'vue'
import { useResourcesStore } from '@/stores/resources'
import { useIoTStore } from '@/stores/iot'
import { useOrdersStore } from '@/stores/orders'
import { useCountUp } from '@/composables/useCountUp'

const resources = useResourcesStore()
const iot = useIoTStore()
const orders = useOrdersStore()

const total = useCountUp(() => resources.items.length)
const available = useCountUp(() => resources.available.length)
const devices = useCountUp(() => iot.latestList.length)
const orderCount = useCountUp(() => orders.items.length)

const stats = computed(() => [
  { label: '资源总数', value: total.value, color: 'cyan' },
  { label: '可用资源', value: available.value, color: 'available' },
  { label: '活跃设备', value: devices.value, color: 'blue' },
  { label: '订单总数', value: orderCount.value, color: 'violet' },
])

const fmt = (n: number) => Math.round(n).toLocaleString('zh-CN')
</script>

<template>
  <div class="panel panel--primary">
    <div class="panel-title">核心指标</div>
    <div class="panel-body stat-grid">
      <div v-for="s in stats" :key="s.label" class="stat-card">
        <div class="stat-value" :class="`stat-${s.color}`">{{ fmt(s.value) }}</div>
        <div class="stat-label">{{ s.label }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
}
.stat-card {
  text-align: center;
  padding: 10px var(--space-1);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  background: rgba(0, 229, 255, 0.05);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.stat-card:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-glow);
}
.stat-value {
  font-family: var(--font-mono);
  font-size: var(--fs-xl);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
}
.stat-cyan      { color: var(--accent-cyan); }
.stat-available { color: var(--status-available); }
.stat-blue      { color: var(--accent); }
.stat-violet    { color: var(--accent-violet); }
.stat-label {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  margin-top: var(--space-1);
}
</style>
