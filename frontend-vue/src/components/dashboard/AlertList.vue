<script setup lang="ts">
import { computed } from 'vue'
import { useIoTStore } from '@/stores/iot'

const iot = useIoTStore()

const levelTag: Record<string, string> = {
  critical: 'tag-red', warn: 'tag-orange', info: 'tag-blue',
}
const list = computed(() => iot.activeAlerts.slice(0, 8))
</script>

<template>
  <div class="panel">
    <div class="panel-title">活跃告警</div>
    <div class="panel-body">
      <div v-if="!list.length" class="empty" style="color: var(--accent-green);">✓ 无活跃告警</div>
      <div v-else class="alert-list">
        <div v-for="a in list" :key="a.id" class="alert-item">
          <span class="tag" :class="levelTag[a.level] || 'tag-blue'">{{ a.level }}</span>
          <span class="msg">{{ a.message }}</span>
          <span class="time">{{ a.created_at.slice(11, 16) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.alert-list { display: flex; flex-direction: column; gap: 6px; max-height: 150px; overflow-y: auto; }
.alert-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px;
  border-left: 2px solid var(--accent-red);
  background: rgba(255, 71, 87, 0.08);
  border-radius: 0 4px 4px 0;
  font-size: 11px;
}
.msg { flex: 1; color: var(--text-primary); }
.time { font-family: 'Consolas', monospace; color: var(--text-muted); font-size: 10px; }
.empty { text-align: center; padding: 16px; font-size: 12px; }
</style>
