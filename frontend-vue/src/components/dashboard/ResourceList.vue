<script setup lang="ts">
import { computed } from 'vue'
import { useResourcesStore } from '@/stores/resources'
import { fmtPrice } from '@/utils/format'
import {
  RESOURCE_STATUS_CLASS,
  RESOURCE_STATUS_LABEL,
  RESOURCE_TYPE_LABEL,
} from '@/utils/labels'
import { useNewItemFlash } from '@/composables/useNewItemFlash'

const resources = useResourcesStore()

const list = computed(() => resources.items.slice(0, 8))
const flashing = useNewItemFlash(() => resources.items.map((r) => r.id))
</script>

<template>
  <div class="panel panel--secondary panel--grow">
    <div class="panel-title">资源列表</div>
    <div class="panel-body">
      <div v-if="!list.length" class="empty">暂无资源</div>
      <div v-else class="res-list">
        <div
          v-for="r in list"
          :key="r.id"
          class="res-item"
          :class="{ 'is-new': flashing.has(String(r.id)) }"
        >
          <div class="res-name">{{ r.name }}</div>
          <div class="res-meta">
            <span class="tag" :class="RESOURCE_STATUS_CLASS[r.status] || 'tag-pending'">
              {{ RESOURCE_STATUS_LABEL[r.status] || r.status }}
            </span>
            <span class="res-type">{{ RESOURCE_TYPE_LABEL[r.type] || r.type }}</span>
            <span v-if="r.price" class="res-price">{{ fmtPrice(r.price, r.price_unit) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.res-list { display: flex; flex-direction: column; gap: 6px; }
.res-item {
  padding: var(--space-2) 10px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-sm);
  background: rgba(64, 158, 255, 0.04);
  transition: background 0.2s, border-color 0.2s;
}
.res-item:hover { background: rgba(64, 158, 255, 0.12); border-color: var(--border-glow); }
.res-name {
  font-size: var(--fs-base);
  color: var(--text-primary);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.res-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-1);
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.res-type { color: var(--accent-cyan); }
.res-price {
  color: var(--accent-orange);
  margin-left: auto;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.empty { text-align: center; color: var(--text-muted); padding: 20px; font-size: var(--fs-sm); }
</style>
