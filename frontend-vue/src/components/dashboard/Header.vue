<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useResourcesStore } from '@/stores/resources'
import { useOrdersStore } from '@/stores/orders'
import { useIoTStore } from '@/stores/iot'
import { http } from '@/api/client'

const resources = useResourcesStore()
const orders = useOrdersStore()
const iot = useIoTStore()

const now = ref(new Date())
let timer: number | null = null
onMounted(() => { timer = window.setInterval(() => (now.value = new Date()), 1000) as unknown as number })
onUnmounted(() => { if (timer) clearInterval(timer) })

// 真实依赖状态：不再硬编码绿灯，Redis/MQTT 不可用时显示为告警色
const healthy = ref(false)
const redisOk = ref(false)
const mqttOk = ref(false)
let healthTimer: number | null = null

async function pollHealth() {
  try {
    const { data } = await http.get('/api/health', { timeout: 4000 })
    healthy.value = data?.status === 'ok'
    redisOk.value = !!data?.redis
    mqttOk.value = !!data?.mqtt
  } catch {
    healthy.value = false
    redisOk.value = false
    mqttOk.value = false
  }
}
onMounted(() => { pollHealth(); healthTimer = window.setInterval(pollHealth, 15000) as unknown as number })
onUnmounted(() => { if (healthTimer) clearInterval(healthTimer) })

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
        <span class="title-main">怀化国际陆港 · 冷链资源智能撮合（虚拟构建）</span>
        <span class="title-sub">HUAIHUA LAND PORT · COLD-CHAIN RESOURCE MATCHING · VIRTUAL BUILD</span>
      </h1>
    </div>

    <div class="header-right">
      <div class="status-chip">
        <span class="dot" :class="healthy ? 'dot-green' : 'dot-red'"></span>
        <span>后端 8002</span>
      </div>
      <div class="status-chip">
        <span class="dot" :class="redisOk ? 'dot-green' : 'dot-amber'"></span>
        <span>Redis {{ redisOk ? '正常' : '降级' }}</span>
      </div>
      <div class="status-chip">
        <span class="dot" :class="mqttOk ? 'dot-green' : 'dot-amber'"></span>
        <span>MQTT {{ mqttOk ? '已连' : '未连' }}</span>
      </div>
      <div class="status-chip">
        <span class="dot dot-cyan"></span>
        <span>IoT {{ iot.latestList.length }}</span>
      </div>
      <div class="status-chip">
        <span class="dot dot-blue"></span>
        <span>资源 {{ resources.items.length }}</span>
      </div>
      <a href="./admin.html#/workbench" class="manage-link">供给工作台 →</a>
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
  font-size: var(--fs-sm);
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
  font-family: var(--font-mono);
  font-size: var(--fs-md);
  color: var(--accent-cyan);
  letter-spacing: 2px;
  font-variant-numeric: tabular-nums;
}

.title { text-align: center; }
.title-main {
  display: block;
  font-size: var(--fs-xl);
  font-weight: 700;
  letter-spacing: 6px;
  background: linear-gradient(90deg, var(--accent-cyan), var(--accent), var(--accent-cyan));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  white-space: nowrap;
}
.title-sub {
  display: block;
  font-size: var(--fs-xs);
  color: var(--text-muted);
  letter-spacing: 4px;
  margin-top: 2px;
  white-space: nowrap;
}

.status-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  padding: 4px 10px;
  border: 1px solid var(--border-soft);
  border-radius: 20px;
  background: rgba(0, 229, 255, 0.05);
  white-space: nowrap;
}
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex: none; }
.dot-green { background: var(--accent-green); box-shadow: 0 0 6px var(--accent-green); animation: pulse 2s infinite; }
.dot-amber { background: var(--alert-warn); box-shadow: 0 0 6px var(--alert-warn); }
.dot-red   { background: var(--alert-critical); box-shadow: 0 0 6px var(--alert-critical); }
.dot-cyan  { background: var(--accent-cyan); box-shadow: 0 0 6px var(--accent-cyan); }
.dot-blue  { background: var(--accent); box-shadow: 0 0 6px var(--accent); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
