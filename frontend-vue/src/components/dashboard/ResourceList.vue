<script setup lang="ts">
import { computed } from 'vue'
import { useResourcesStore } from '@/stores/resources'

const resources = useResourcesStore()

const typeLabels: Record<string, string> = {
  warehouse: '仓库', cold_box: '冷链箱', vehicle: '运力', equipment: '设备',
}
const statusClass: Record<string, string> = {
  available: 'tag-green', booked: 'tag-orange', offline: 'tag-red', pending: 'tag-blue',
}

const list = computed(() => resources.items.slice(0, 8))
</script>

<template>
  <div class="panel">
    <div class="panel-title">资源列表</div>
    <div class="panel-body">
      <div v-if="!list.length" class="empty">暂无资源</div>
      <div v-else class="res-list">
        <div v-for="r in list" :key="r.id" class="res-item">
          <div class="res-name">{{ r.name }}</div>
          <div class="res-meta">
            <span class="tag" :class="statusClass[r.status] || 'tag-blue'">{{ r.status }}</span>
            <span class="res-type">{{ typeLabels[r.type] || r.type }}</span>
            <span v-if="r.price" class="res-price">¥{{ r.price }}/{{ r.price_unit || '天' }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.res-list { display: flex; flex-direction: column; gap: 6px; max-height: 260px; overflow-y: auto; }
.res-item {
  padding: 8px 10px;
  border: 1px solid var(--border-glow);
  border-radius: 4px;
  background: rgba(64, 158, 255, 0.04);
  transition: background 0.2s;
}
.res-item:hover { background: rgba(64, 158, 255, 0.12); }
.res-name { font-size: 13px; color: var(--text-primary); font-weight: 600; }
.res-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-secondary);
}
.res-type { color: var(--accent-cyan); }
.res-price { color: var(--accent-orange); margin-left: auto; font-family: 'Consolas', monospace; }
.empty { text-align: center; color: var(--text-muted); padding: 20px; font-size: 12px; }
</style>
