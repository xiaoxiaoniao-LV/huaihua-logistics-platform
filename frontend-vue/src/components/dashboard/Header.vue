<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useResourcesStore } from '@/stores/resources'
import { useOrdersStore } from '@/stores/orders'
import { useIoTStore } from '@/stores/iot'

const resources = useResourcesStore()
const orders = useOrdersStore()
const iot = useIoTStore()

const now = ref(new Date())
let timer: number | null = null
onMounted(() => { timer = window.setInterval(() => (now.value = new Date()), 1000) as unknown as number })
onUnmounted(() => { if (timer) clearInterval(timer) })

const fmt = (d: Date) => {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
</script>

<template>
  <header class="header">
    <div class="header-left">
      <div class="sys-time">{{ fmt(now) }}</div>
    </div>

    <div class="header-center">
      <h1 class="title">
        <span class="title-main">怀化国际陆港 · 数字孪生大屏</span>
        <span class="title-sub">HUAIHUA INTERNATIONAL LAND PORT · DIGITAL TWIN</span>
      </h1>
    </div>

    <div class="header-right">
      <div class="status-chip">
        <span class="dot dot-green"></span>
        <span>后端 8002</span>
      </div>
      <div class="status-chip">
        <span class="dot dot-green"></span>
        <span>Redis 6379</span>
      </div>
      <div class="status-chip">
        <span class="dot dot-cyan"></span>
        <span>IoT {{ iot.latestList.length }}</span>
      </div>
      <div class="status-chip">
        <span class="dot dot-blue"></span>
        <span>资源 {{ resources.items.length }}</span>
      </div>
      <RouterLink to="/manage/resources" class="manage-link">运营管理 →</RouterLink>
    </div>
  </header>
</template>

<style scoped>
.header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  border-bottom: 1px solid var(--border-glow);
  background: linear-gradient(180deg, rgba(10, 26, 54, 0.95), rgba(5, 13, 31, 0.95));
}

.header-left { width: 280px; display: flex; align-items: center; gap: 12px; }
.header-right {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.manage-link {
  color: var(--accent-cyan);
  text-decoration: none;
  font-size: 12px;
  padding: 5px 12px;
  border: 1px solid var(--border-glow);
  border-radius: 20px;
  background: rgba(0, 229, 255, 0.06);
  transition: all 0.2s;
  white-space: nowrap;
}
.manage-link:hover {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 10px rgba(0, 229, 255, 0.3);
}

.sys-time {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 14px;
  color: var(--accent-cyan);
  letter-spacing: 2px;
}

.title { text-align: center; }
.title-main {
  display: block;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 6px;
  background: linear-gradient(90deg, var(--accent-cyan), var(--accent), var(--accent-cyan));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.title-sub {
  display: block;
  font-size: 10px;
  color: var(--text-muted);
  letter-spacing: 4px;
  margin-top: 2px;
}

.status-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  padding: 4px 10px;
  border: 1px solid var(--border-glow);
  border-radius: 20px;
  background: rgba(0, 229, 255, 0.05);
}
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-green { background: var(--accent-green); box-shadow: 0 0 6px var(--accent-green); animation: pulse 2s infinite; }
.dot-cyan  { background: var(--accent-cyan); box-shadow: 0 0 6px var(--accent-cyan); }
.dot-blue  { background: var(--accent); box-shadow: 0 0 6px var(--accent); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
