<script setup lang="ts">
import { computed } from 'vue'
import { useOrdersStore } from '@/stores/orders'
import { ORDER_STATUS_CLASS, ORDER_STATUS_LABEL } from '@/utils/labels'
import { useNewItemFlash } from '@/composables/useNewItemFlash'

const orders = useOrdersStore()

const list = computed(() => orders.items.slice(0, 6))
const flashing = useNewItemFlash(() => orders.items.map((o) => o.id))

const statusText = (s: string) => ORDER_STATUS_LABEL[s] || '未知状态'
const statusClass = (s: string) => ORDER_STATUS_CLASS[s] || 'tag-pending'
</script>

<template>
  <div class="panel panel--secondary panel--grow">
    <div class="panel-title">最近订单</div>
    <div class="panel-body">
      <div v-if="!list.length" class="empty">暂无订单</div>
      <div v-else class="order-list">
        <div
          v-for="o in list"
          :key="o.id"
          class="order-item"
          :class="{ 'is-new': flashing.has(String(o.id)) }"
        >
          <div class="order-head">
            <span class="oid">#{{ o.id }}</span>
            <span class="tag" :class="statusClass(o.status)">{{ statusText(o.status) }}</span>
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
.order-list { display: flex; flex-direction: column; gap: 6px; }
.order-item {
  padding: var(--space-2) 10px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-sm);
  background: rgba(64, 158, 255, 0.04);
}
.order-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-sm);
}
.oid {
  font-family: var(--font-mono);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
.price {
  margin-left: auto;
  font-family: var(--font-mono);
  color: var(--accent-orange);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.order-time {
  display: flex;
  gap: 6px;
  margin-top: var(--space-1);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.arrow { color: var(--accent-cyan); }
.empty { text-align: center; color: var(--text-muted); padding: var(--space-4); font-size: var(--fs-sm); }
</style>
