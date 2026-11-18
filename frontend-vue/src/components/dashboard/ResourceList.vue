<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useResourcesStore } from '@/stores/resources'
import { useTwinStore } from '@/stores/twin'
import { fmtPrice } from '@/utils/format'
import {
  RESOURCE_STATUS_CLASS,
  RESOURCE_STATUS_LABEL,
  RESOURCE_TYPE_LABEL,
} from '@/utils/labels'
import { useNewItemFlash } from '@/composables/useNewItemFlash'

const resources = useResourcesStore()
const twin = useTwinStore()

const PAGE_SIZE = 8
const page = ref(0)
const totalPages = computed(() => Math.max(1, Math.ceil(resources.items.length / PAGE_SIZE)))
const list = computed(() =>
  resources.items.slice(page.value * PAGE_SIZE, (page.value + 1) * PAGE_SIZE),
)
const flashing = useNewItemFlash(() => resources.items.map((r) => r.id))

watch(totalPages, (total) => {
  if (page.value > total - 1) page.value = total - 1
})

function turn(delta: number) {
  page.value = Math.min(totalPages.value - 1, Math.max(0, page.value + delta))
}

/** 点击资源 → 三维舞台定位到对应货位 */
function locate(id: number) {
  twin.focusResource(id)
}
</script>

<template>
  <div class="panel panel--secondary panel--grow">
    <div class="panel-title">
      资源列表
      <span class="count">{{ resources.items.length }}</span>
    </div>
    <div class="panel-body">
      <div v-if="!list.length" class="empty">暂无资源</div>
      <div v-else class="res-list">
        <div
          v-for="r in list"
          :key="r.id"
          class="res-item"
          :class="{ 'is-new': flashing.has(String(r.id)), 'is-focus': twin.focusResourceId === r.id }"
          @click="locate(r.id)"
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
    <div v-if="totalPages > 1" class="pager">
      <button class="page-btn" :disabled="page === 0" @click="turn(-1)">‹</button>
      <span class="page-info">{{ page + 1 }} / {{ totalPages }}</span>
      <button class="page-btn" :disabled="page >= totalPages - 1" @click="turn(1)">›</button>
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
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}
.res-item:hover { background: rgba(64, 158, 255, 0.12); border-color: var(--border-glow); }
.res-item.is-focus {
  background: rgba(0, 229, 255, 0.1);
  border-color: var(--accent-cyan);
  box-shadow: 0 0 10px rgba(0, 229, 255, 0.18);
}
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
.count {
  float: right;
  font-size: var(--fs-xs);
  color: var(--text-muted);
  font-weight: 400;
}
.empty { text-align: center; color: var(--text-muted); padding: 20px; font-size: var(--fs-sm); }

.pager {
  display: flex; align-items: center; justify-content: center; gap: 10px;
  padding-top: 6px; border-top: 1px solid var(--border-soft);
}
.page-btn {
  width: 24px; height: 22px; cursor: pointer;
  border: 1px solid var(--border-soft); border-radius: var(--radius-sm);
  background: var(--bg-card-soft); color: var(--text-secondary);
}
.page-btn:hover:not(:disabled) { color: var(--accent-cyan); border-color: var(--border-glow); }
.page-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.page-info { font-size: var(--fs-xs); color: var(--text-muted); font-variant-numeric: tabular-nums; }
</style>
