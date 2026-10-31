<script setup lang="ts">
import { computed } from 'vue'
import { useOrdersStore } from '@/stores/orders'

const orders = useOrdersStore()

const statusLabel: Record<string, string> = {
  pending: 'tag-blue', confirmed: 'tag-green', ongoing: 'tag-green',
  finished: 'tag-green', cancelled: 'tag-red',
}
const list = computed(() => orders.items.slice(0, 6))
</script>

<template>
  <div class="panel">
    <div class="panel-title">最近订单</div>
    <div class="panel-body">
      <div v-if="!list.length" class="empty">暂无订单</div>
      <div v-else class="order-list">
        <div v-for="o in list" :key="o.id" class="order-item">
          <div class="order-head">
            <span class="oid">#{{ o.id }}</span>
            <span class="tag" :class="statusLabel[o.status] || 'tag-blue'">{{ o.status }}</span>
            <span v-if="o.total_price" class="price">¥{{ o.total_price }}</span>
          </div>
          <div class="order-time">
            <span>{{ o.start_time?.slice(5, 16) || '-' }}</span>
            <span class="arrow">→</span>
            <span>{{ o.end_time?.slice(5, 16) || '-' }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.order-list { display: flex; flex-direction: column; gap: 6px; max-height: 180px; overflow-y: auto; }
.order-item {
  padding: 8px 10px;
  border: 1px solid var(--border-glow);
  border-radius: 4px;
  background: rgba(64, 158, 255, 0.04);
}
.order-head {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px;
}
.oid { font-family: 'Consolas', monospace; color: var(--text-muted); }
.price { margin-left: auto; font-family: 'Consolas', monospace; color: var(--accent-orange); font-weight: 600; }
.order-time {
  display: flex; gap: 6px; margin-top: 4px;
  font-size: 11px; color: var(--text-secondary); font-family: 'Consolas', monospace;
}
.arrow { color: var(--accent-cyan); }
.empty { text-align: center; color: var(--text-muted); padding: 16px; font-size: 12px; }
</style>
