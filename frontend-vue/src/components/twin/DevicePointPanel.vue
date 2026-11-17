<script setup lang="ts">
/** 设备点位实时面板：大屏右下角浮层，展示单个设备的全量测点、趋势与事件。 */
import { computed, ref, watch } from 'vue'
import { fetchDeviceSeries, type SeriesPoint } from '@/api/twin'
import { useTwinStore } from '@/stores/twin'
import { TWIN_STATUS_TEXT } from '@/core/TwinLevelScene'

const twin = useTwinStore()

const selectedPoint = ref<string>('')
const series = ref<SeriesPoint[]>([])
const seriesLoading = ref(false)

const detail = computed(() => twin.deviceDetail)
const numericPoints = computed(() =>
  (detail.value?.points || []).filter((p) => p.data_type === 'number'),
)
const activePoint = computed(
  () => detail.value?.points.find((p) => p.point_key === selectedPoint.value) || null,
)

watch(
  () => twin.selectedDevice,
  () => {
    const first = numericPoints.value[0]
    selectedPoint.value = first?.point_key || ''
    loadSeries()
  },
  { immediate: true },
)

watch(selectedPoint, () => loadSeries())

async function loadSeries() {
  if (!detail.value || !selectedPoint.value) {
    series.value = []
    return
  }
  seriesLoading.value = true
  try {
    const { data } = await fetchDeviceSeries(detail.value.device_code, selectedPoint.value, 48)
    series.value = data.data
  } catch {
    series.value = []
  } finally {
    seriesLoading.value = false
  }
}

const chart = computed(() => {
  const nums = series.value
    .map((p) => ({ ts: p.ts, v: p.value_num }))
    .filter((p): p is { ts: string; v: number } => p.v !== null)
  if (nums.length < 2) return null
  const values = nums.map((p) => p.v)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const w = 260
  const h = 62
  const points = nums
    .map((p, i) => {
      const x = (i / (nums.length - 1)) * w
      const y = h - ((p.v - min) / span) * (h - 8) - 4
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return { points, w, h, min, max }
})

function fmtValue(p: { value: unknown; data_type: string; unit: string | null }) {
  if (p.value === null || p.value === undefined) return '--'
  if (p.data_type === 'bool') return p.value ? '开' : '关'
  if (p.data_type === 'text') return String(p.value)
  return `${p.value}${p.unit || ''}`
}

function fmtAge(ms: number | null) {
  if (ms === null || ms === undefined) return '从未上报'
  if (ms < 60000) return '刚刚'
  if (ms < 3600000) return `${Math.floor(ms / 60000)} 分钟前`
  if (ms < 86400000) return `${Math.floor(ms / 3600000)} 小时前`
  return `${Math.floor(ms / 86400000)} 天前`
}

function rangePos(p: { value: unknown; min_value: number | null; max_value: number | null }) {
  if (typeof p.value !== 'number' || p.min_value === null || p.max_value === null) return null
  const span = p.max_value - p.min_value
  if (!span) return null
  return Math.min(100, Math.max(0, ((p.value - p.min_value) / span) * 100))
}

function close() {
  twin.selectDevice(null)
}
</script>

<template>
  <div v-if="detail || twin.selectedDevice" class="device-panel">
    <header class="panel-head">
      <div class="title-block">
        <div class="device-name">{{ detail?.name || twin.selectedDevice }}</div>
        <div class="device-meta">
          <span class="code">{{ detail?.device_code }}</span>
          <span class="dot" :class="detail?.status || 'unknown'" />
          <span>{{ TWIN_STATUS_TEXT[detail?.status || 'unknown'] }}</span>
          <span class="sep">·</span>
          <span>{{ fmtAge(detail?.age_ms ?? null) }}</span>
        </div>
      </div>
      <button class="close-btn" title="关闭" @click="close">×</button>
    </header>

    <div class="points">
      <button
        v-for="p in detail?.points || []"
        :key="p.point_key"
        class="point-card"
        :class="{ active: p.point_key === selectedPoint, warn: p.quality !== 'good' }"
        @click="p.data_type === 'number' && (selectedPoint = p.point_key)"
      >
        <div class="point-label">{{ p.name }}</div>
        <div class="point-value">{{ fmtValue(p) }}</div>
        <div v-if="rangePos(p) !== null" class="range">
          <span class="range-fill" :style="{ width: rangePos(p) + '%' }" />
        </div>
      </button>
      <div v-if="!detail?.points.length" class="empty">该设备尚未上报点位</div>
    </div>

    <section v-if="activePoint" class="trend">
      <div class="section-title">
        <span>{{ activePoint.name }} 趋势</span>
        <span class="range-text">
          {{ activePoint.min_value ?? '--' }} ~ {{ activePoint.max_value ?? '--' }}{{ activePoint.unit || '' }}
        </span>
      </div>
      <svg v-if="chart" :viewBox="`0 0 ${chart.w} ${chart.h}`" class="spark" preserveAspectRatio="none">
        <polyline :points="chart.points" fill="none" stroke="var(--accent-cyan)" stroke-width="1.6" />
        <polyline
          :points="`0,${chart.h} ${chart.points} ${chart.w},${chart.h}`"
          fill="rgba(0,229,255,.12)"
          stroke="none"
        />
      </svg>
      <div v-else class="empty small">
        {{ seriesLoading ? '趋势加载中…' : '暂无足够历史点位（至少 2 条）' }}
      </div>
    </section>

    <section class="events">
      <div class="section-title"><span>最近事件</span></div>
      <ul>
        <li v-for="e in twin.deviceEvents.slice(0, 6)" :key="e.id">
          <span class="evt-dot" :class="e.severity" />
          <span class="evt-type">{{ e.message || e.event_type }}</span>
          <span class="evt-time">{{ e.ts ? e.ts.slice(11, 19) : '' }}</span>
        </li>
        <li v-if="!twin.deviceEvents.length" class="empty small">暂无事件</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.device-panel {
  position: absolute;
  top: 56px;
  right: 12px;
  bottom: 12px;
  width: 312px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border-glow);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  backdrop-filter: blur(10px);
  box-shadow: var(--shadow-panel);
  overflow-y: auto;
  z-index: 5;
}

.panel-head { display: flex; align-items: flex-start; justify-content: space-between; }
.device-name { font-size: var(--fs-md); font-weight: 600; color: var(--text-primary); }
.device-meta {
  display: flex; align-items: center; gap: 6px; margin-top: 4px;
  font-size: var(--fs-xs); color: var(--text-secondary);
}
.code { font-family: var(--font-mono); color: var(--accent-cyan); }
.sep { opacity: 0.4; }

.dot { width: 7px; height: 7px; border-radius: 50%; background: var(--status-pending); }
.dot.online { background: var(--accent-green); box-shadow: 0 0 6px var(--accent-green); }
.dot.alarm { background: var(--alert-critical); box-shadow: 0 0 6px var(--alert-critical); }
.dot.degraded { background: var(--alert-warn); }
.dot.offline { background: var(--status-offline); }
.dot.maintenance { background: var(--accent-violet); }

.close-btn {
  border: none; background: transparent; color: var(--text-secondary);
  font-size: 20px; line-height: 1; cursor: pointer; padding: 0 4px;
}
.close-btn:hover { color: var(--text-primary); }

.points { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.point-card {
  text-align: left; padding: 7px 9px; cursor: default;
  border: 1px solid var(--border-soft); border-radius: var(--radius-md);
  background: var(--bg-inset); color: inherit;
  transition: border-color 0.2s, background 0.2s;
}
.point-card.active { border-color: var(--accent-cyan); background: var(--bg-card-hover); }
.point-card.warn { border-color: var(--alert-critical); }
.point-label { font-size: var(--fs-xs); color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.point-value {
  margin-top: 2px; font-size: var(--fs-lg); font-weight: 600; color: var(--text-primary);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.range { margin-top: 5px; height: 3px; border-radius: 2px; background: rgba(255, 255, 255, 0.08); overflow: hidden; }
.range-fill { display: block; height: 100%; background: linear-gradient(90deg, var(--accent-cyan), var(--accent-green)); }

.trend, .events { border-top: 1px solid var(--border-soft); padding-top: 8px; }
.section-title {
  display: flex; justify-content: space-between; align-items: center;
  font-size: var(--fs-xs); color: var(--text-secondary); letter-spacing: 0.5px; margin-bottom: 6px;
}
.range-text { color: var(--text-muted); }
.spark { width: 100%; height: 64px; }

.events ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 5px; }
.events li { display: flex; align-items: center; gap: 6px; font-size: var(--fs-xs); color: var(--text-secondary); }
.evt-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--border-glow); flex: none; }
.evt-dot.warn { background: var(--alert-warn); }
.evt-dot.critical { background: var(--alert-critical); }
.evt-type { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.evt-time { color: var(--text-muted); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }

.empty { grid-column: 1 / -1; font-size: var(--fs-xs); color: var(--text-muted); padding: 8px 0; }
.empty.small { padding: 2px 0; }
</style>
