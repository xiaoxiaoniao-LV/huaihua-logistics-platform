<script setup lang="ts">
/** 中央孪生舞台：园区 → 货位 → 设备三级下钻 + 真实 GLB + 左右栏双向联动。 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  TwinLevelScene, type TwinNodeLite, type TwinStageKind, TWIN_STATUS_TEXT,
} from '@/core/TwinLevelScene'
import { useTwinStore } from '@/stores/twin'
import DevicePointPanel from '@/components/twin/DevicePointPanel.vue'
import { slotCode, slotRow } from '@/utils/labels'
import type { TwinNode } from '@/api/twin'

const twin = useTwinStore()
const canvasRef = ref<HTMLCanvasElement | null>(null)
const wrapRef = ref<HTMLElement | null>(null)
const loadingModel = ref(false)
const isFullscreen = ref(false)
/** 浏览模式默认开启：单击不下钻，只有双击聚焦，杜绝拖拽后的误触 */
const mode = ref<'browse' | 'operate'>('browse')
const indexOpen = ref(true)
const slotQuery = ref('')

let scene: TwinLevelScene | null = null
let pollTimer: number | null = null
let currentSig = ''
let syncChain: Promise<void> = Promise.resolve()

/** 园区根节点只有一个 site 时，直接展开成楼栋，少点一次 */
const levelNodes = computed<TwinNode[]>(() => {
  const nodes = twin.currentNodes
  const first = nodes[0]
  if (
    !twin.breadcrumb.length &&
    nodes.length === 1 &&
    first?.node_type === 'site' &&
    first.children.length
  ) {
    return first.children
  }
  return nodes
})

const breadcrumb = computed(() => twin.breadcrumb)
/** 面包屑不重复显示园区根节点 */
const crumbPath = computed(() =>
  breadcrumb.value
    .map((node, index) => ({ node, index }))
    .filter((item) => item.node.node_type !== 'site'),
)

const stageKind = computed<TwinStageKind>(() => {
  const last = breadcrumb.value[breadcrumb.value.length - 1]
  if (!last || last.node_type === 'site') return 'park'
  return 'coldroom'
})

const summary = computed(() => twin.summary)
const legend = [
  { key: 'online', label: '在线' },
  { key: 'alarm', label: '告警' },
  { key: 'degraded', label: '数据异常' },
  { key: 'offline', label: '离线' },
  { key: 'maintenance', label: '维护' },
  { key: 'unknown', label: '待接入' },
]
const summaryItems = computed(() =>
  legend
    .map((l) => ({ ...l, count: summary.value[l.key] || 0 }))
    .filter((l) => l.count > 0 || l.key === 'online' || l.key === 'alarm'),
)

const stripNodes = computed(() => levelNodes.value.slice(0, 30))
const stripHidden = computed(() => Math.max(0, levelNodes.value.length - stripNodes.value.length))

/** 当前层级里的货位节点，供编号速查使用 */
const slotNodes = computed(() => levelNodes.value.filter((n) => n.node_type === 'slot'))

const slotGroups = computed(() => {
  const q = slotQuery.value.trim().toLowerCase()
  const groups = new Map<string, Array<{ node: TwinNode; code: string }>>()
  slotNodes.value.forEach((node) => {
    const anchor = node.transform?.anchor as string | undefined
    const code = slotCode(anchor)
    if (!code) return
    if (q && !`${code}${node.name}`.toLowerCase().includes(q)) return
    const row = slotRow(anchor) || '--'
    let list = groups.get(row)
    if (!list) {
      list = []
      groups.set(row, list)
    }
    list.push({ node, code })
  })
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([row, items]) => ({ row, items }))
})

const tipText = computed(() => {
  if (stageKind.value === 'park') {
    return mode.value === 'browse'
      ? '浏览模式：拖拽旋转 · 滚轮缩放 · 双击聚焦'
      : '操作模式：单击冷库进入库内 · 双击聚焦'
  }
  return mode.value === 'browse'
    ? '浏览模式：拖拽查看货架 · 双击聚焦 · 切到操作模式可点选货位'
    : '操作模式：单击货位定位设备 · 双击聚焦 · Esc 返回'
})

function setMode(next: 'browse' | 'operate') {
  mode.value = next
  scene?.setInteractionMode(next)
}

function locateSlot(node: TwinNode) {
  twin.focusSlot(node)
  scene?.focusNode(node.node_key)
}

function toLite(node: TwinNode): TwinNodeLite {
  return {
    node_key: node.node_key,
    name: node.name,
    node_type: node.node_type,
    status: node.status,
    model_ref: node.model_ref ?? null,
    transform: node.transform ?? null,
    children: node.children.map(toLite),
    bindings: node.bindings.map((b) => ({
      point_key: b.point_key,
      name: b.name,
      value: b.value,
      unit: b.unit,
      quality: b.quality,
      device_code: b.device_code,
    })),
  }
}

function selectedKey(): string | null {
  const highlight = twin.highlightKey
  if (highlight && levelNodes.value.some((n) => n.node_key === highlight)) return highlight
  const code = twin.selectedDevice
  if (!code) return null
  const hit = levelNodes.value.find((n) => n.bindings.some((b) => b.device_code === code))
  return hit?.node_key || null
}

/** 串行执行场景同步，避免模型加载期间多次下钻互相覆盖 */
function syncScene() {
  syncChain = syncChain.then(runSync).catch(() => {})
  return syncChain
}

async function runSync() {
  if (!scene) return
  const kind = stageKind.value
  const nodes = levelNodes.value.map(toLite)
  const sig = `${kind}|${nodes.map((n) => n.node_key).join(',')}`

  if (sig !== currentSig) {
    currentSig = sig
    loadingModel.value = true
    await scene.setStage(kind, nodes)
    loadingModel.value = false
  } else {
    scene.updateValues(nodes)
  }
  scene.setSelected(selectedKey())
}

function onPick(nodeKey: string | null) {
  if (!nodeKey) {
    scene?.setSelected(null)
    return
  }
  const node = levelNodes.value.find((n) => n.node_key === nodeKey)
  if (!node) return
  scene?.setSelected(nodeKey)

  // 货位：与左栏资源列表保持同一路径，停在库房层并高亮货位
  if (node.node_type === 'slot') {
    locateSlot(node)
    return
  }
  if (node.node_type === 'device') {
    const device = node.bindings[0]?.device_code
    if (device) twin.selectDevice(device)
    return
  }
  if (node.children.length) {
    twin.drill(node)
  }
}

function goRoot() {
  twin.reset()
}

function goPath(index: number) {
  twin.upTo(index + 1)
}

function goUp() {
  if (!breadcrumb.value.length) return
  twin.upTo(breadcrumb.value.length - 1)
}

async function refresh() {
  await twin.fetchSnapshot()
}

async function toggleFullscreen() {
  const el = (wrapRef.value?.parentElement || wrapRef.value) as HTMLElement | null
  if (!document.fullscreenElement) await el?.requestFullscreen?.()
  else await document.exitFullscreen()
}

function resetView() {
  scene?.resetView()
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') goUp()
}

watch(levelNodes, () => nextTick(syncScene), { deep: true })

watch(
  () => twin.highlightKey,
  async (key) => {
    if (!key) return
    await nextTick()
    await syncScene()
    if (levelNodes.value.some((n) => n.node_key === key)) {
      scene?.setSelected(key)
      scene?.focusNode(key)
    }
  },
)

watch(
  () => twin.selectedDevice,
  () => scene?.setSelected(selectedKey()),
)

onMounted(async () => {
  if (!twin.snapshot) await twin.fetchSnapshot()
  await nextTick()
  if (!canvasRef.value) return

  scene = new TwinLevelScene(canvasRef.value)
  scene.init()
  scene.setPickCallback(onPick)
  scene.setInteractionMode(mode.value)
  await syncScene()

  document.addEventListener('fullscreenchange', onFullscreenChange)
  window.addEventListener('keydown', onKeydown)

  pollTimer = window.setInterval(() => {
    twin.fetchSnapshot()
  }, 10000) as unknown as number
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  window.removeEventListener('keydown', onKeydown)
  scene?.dispose()
  scene = null
})
</script>

<template>
  <div ref="wrapRef" class="twin-stage">
    <!-- 顶部：面包屑 + 状态汇总 -->
    <div class="stage-head">
      <nav class="crumbs">
        <button class="crumb" :class="{ active: !breadcrumb.length }" @click="goRoot">园区总览</button>
        <template v-for="item in crumbPath" :key="item.node.node_key">
          <span class="arrow">›</span>
          <button
            class="crumb"
            :class="{ active: item.index === breadcrumb.length - 1 }"
            @click="goPath(item.index)"
          >
            {{ item.node.name }}
          </button>
        </template>
      </nav>

      <div class="head-right">
        <span v-if="loadingModel" class="loading-chip">模型加载中</span>
        <div class="mode-switch" :class="mode">
          <button
            :class="{ on: mode === 'browse' }"
            title="浏览模式：单击不会下钻，防误触"
            @click="setMode('browse')"
          >浏览</button>
          <button
            :class="{ on: mode === 'operate' }"
            title="操作模式：单击货位定位设备"
            @click="setMode('operate')"
          >操作</button>
        </div>
        <div class="chips">
          <span v-for="item in summaryItems" :key="item.key" class="chip" :class="item.key">
            <i />{{ item.label }} {{ item.count }}
          </span>
        </div>
        <button class="tool" title="复位视角" @click="resetView">⟲</button>
        <button class="tool" :title="isFullscreen ? '退出全屏' : '全屏'" @click="toggleFullscreen">
          {{ isFullscreen ? '⤢' : '⛶' }}
        </button>
        <button class="refresh" :class="{ spinning: twin.loading }" title="刷新孪生数据" @click="refresh">
          ⟳
        </button>
      </div>
    </div>

    <canvas ref="canvasRef" class="stage-canvas" />

    <!-- 操作提示 -->
    <div class="stage-tip">{{ tipText }}</div>

    <!-- 货位编号速查：按排分组，点击直达对应货位 -->
    <div v-if="slotNodes.length" class="slot-index" :class="{ collapsed: !indexOpen }">
      <button class="index-head" @click="indexOpen = !indexOpen">
        <span>编号速查</span>
        <span class="index-toggle">{{ indexOpen ? '收起' : `${slotNodes.length} 个货位` }}</span>
      </button>
      <template v-if="indexOpen">
        <input v-model="slotQuery" class="index-search" placeholder="搜索编号 / 名称" />
        <div class="index-body">
          <div v-for="g in slotGroups" :key="g.row" class="index-group">
            <div class="index-row">{{ g.row }} 排<span>{{ g.items.length }}</span></div>
            <div class="index-codes">
              <button
                v-for="item in g.items"
                :key="item.node.node_key"
                class="index-code"
                :class="[item.node.status, { active: twin.highlightKey === item.node.node_key }]"
                :title="`${item.node.name} · ${item.code}`"
                @click="locateSlot(item.node)"
              >{{ item.code }}</button>
            </div>
          </div>
          <div v-if="!slotGroups.length" class="index-empty">没有匹配的货位编号</div>
        </div>
      </template>
    </div>

    <!-- 图例 -->
    <div class="legend">
      <span v-for="l in legend" :key="l.key" class="legend-item">
        <i :class="l.key" />{{ l.label }}
      </span>
    </div>

    <!-- 当前层级节点列表：三维看不清时可直接点选 -->
    <div class="node-strip">
      <button
        v-for="node in stripNodes"
        :key="node.node_key"
        class="node-pill"
        :class="[node.status, { selected: twin.deviceDetail && node.bindings.some((b) => b.device_code === twin.selectedDevice) }]"
        @click="onPick(node.node_key)"
      >
        <span class="pill-name">{{ node.name }}</span>
        <span class="pill-meta">
          {{ TWIN_STATUS_TEXT[node.status] }}
          <template v-if="node.children.length"> · {{ node.children.length }} 下级</template>
        </span>
      </button>
      <span v-if="stripHidden" class="empty-hint">还有 {{ stripHidden }} 个，请在三维场景中点选</span>
      <span v-if="!levelNodes.length" class="empty-hint">本级暂无孪生节点</span>
    </div>

    <!-- 设备点位面板 -->
    <DevicePointPanel v-if="twin.selectedDevice" />

    <!-- 无数据兜底 -->
    <div v-if="!twin.hasTree && !twin.loading" class="stage-empty">
      <div class="empty-title">尚未配置数字孪生节点</div>
      <div class="empty-desc">
        通过 <code>POST /api/v1/twin/nodes</code> 与 <code>/twin/bindings</code> 建立园区 → 库区 → 库房 → 设备的层级，
        绑定设备点位后即可在此实时下钻。
      </div>
    </div>
  </div>
</template>

<style scoped>
.twin-stage {
  position: absolute;
  inset: 0;
  overflow: hidden;
  /* 与主场景一致的深空网格底，避免切换视角时背景突变 */
  background-color: var(--bg-deep);
  background-image:
    radial-gradient(circle at 50% 30%, rgba(0, 229, 255, 0.08), transparent 60%),
    linear-gradient(rgba(0, 229, 255, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 229, 255, 0.045) 1px, transparent 1px);
  background-size: auto, 48px 48px, 48px 48px;
}

.stage-canvas { width: 100%; height: 100%; display: block; }

.stage-head {
  position: absolute;
  top: 0; left: 0; right: 0;
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 14px;
  background: linear-gradient(180deg, rgba(3, 10, 23, 0.9), transparent);
  z-index: 4;
}

.crumbs { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.crumb {
  border: none; background: transparent; cursor: pointer;
  color: var(--text-secondary); font-size: var(--fs-sm); padding: 3px 6px; border-radius: var(--radius-sm);
}
.crumb:hover { color: var(--text-primary); background: var(--bg-card-hover); }
.crumb.active { color: var(--accent-cyan); font-weight: 600; }
.arrow { color: var(--text-muted); font-size: var(--fs-sm); }

.head-right { display: flex; align-items: center; gap: 10px; }
.chips { display: flex; gap: 6px; }
.chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 999px; font-size: var(--fs-xs);
  color: var(--text-secondary); background: var(--bg-card-soft);
  border: 1px solid var(--border-soft);
}
.chip i, .legend-item i { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }

i.online { background: var(--accent-green); box-shadow: 0 0 6px var(--accent-green); }
i.alarm { background: var(--alert-critical); box-shadow: 0 0 6px var(--alert-critical); }
i.degraded { background: var(--alert-warn); }
i.offline { background: var(--status-offline); }
i.maintenance { background: var(--accent-violet); }
i.unknown { background: var(--status-pending); }

.refresh {
  border: 1px solid var(--border-glow); background: var(--bg-card-soft);
  color: var(--accent-cyan); width: 26px; height: 26px; border-radius: var(--radius-md); cursor: pointer;
}
.refresh:hover { background: var(--bg-card-hover); }
.refresh.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.tool {
  border: 1px solid var(--border-soft); background: var(--bg-card-soft);
  color: var(--text-secondary); width: 26px; height: 26px; border-radius: var(--radius-md);
  cursor: pointer; font-size: 13px; line-height: 1;
}
.tool:hover { color: var(--accent-cyan); border-color: var(--border-glow); background: var(--bg-card-hover); }

.mode-switch {
  display: inline-flex; gap: 2px; padding: 2px;
  border: 1px solid var(--border-soft); border-radius: 999px;
  background: var(--bg-card-soft);
}
.mode-switch button {
  border: none; background: transparent; cursor: pointer;
  color: var(--text-muted); font-size: var(--fs-xs);
  padding: 2px 9px; border-radius: 999px;
}
.mode-switch button:hover { color: var(--text-primary); }
.mode-switch button.on {
  background: rgba(0, 229, 255, 0.14);
  color: var(--accent-cyan); font-weight: 600;
}

.loading-chip {
  font-size: var(--fs-xs); color: var(--accent-cyan);
  padding: 2px 8px; border-radius: 999px;
  background: rgba(0, 229, 255, 0.08); border: 1px solid var(--border-glow);
}

.stage-tip {
  position: absolute; left: 14px; top: 48px;
  font-size: var(--fs-xs); color: var(--text-muted);
  padding: 3px 8px; border-radius: var(--radius-sm);
  background: rgba(4, 16, 34, 0.55); border: 1px solid var(--border-soft);
  pointer-events: none; z-index: 3;
}

/* 货位编号速查：左侧浮动面板，按排分组 */
.slot-index {
  position: absolute; left: 12px; top: 84px; width: 214px;
  max-height: calc(100% - 178px);
  display: flex; flex-direction: column;
  border-radius: var(--radius-md);
  background: rgba(4, 16, 34, 0.8);
  border: 1px solid var(--border-soft);
  backdrop-filter: blur(6px);
  z-index: 3; overflow: hidden;
}
.slot-index.collapsed { width: auto; }
.index-head {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 6px 10px; cursor: pointer;
  border: none; background: transparent; color: var(--text-primary);
  font-size: var(--fs-sm); font-weight: 600;
}
.index-toggle { font-size: var(--fs-xs); color: var(--text-muted); font-weight: 400; }
.index-search {
  margin: 0 8px 6px; padding: 4px 8px;
  border: 1px solid var(--border-soft); border-radius: var(--radius-sm);
  background: var(--bg-card-soft); color: var(--text-primary);
  font-size: var(--fs-xs); outline: none;
}
.index-search:focus { border-color: var(--border-glow); }
.index-body { overflow-y: auto; padding: 0 8px 8px; }
.index-body::-webkit-scrollbar { width: 4px; }
.index-body::-webkit-scrollbar-thumb { background: var(--border-glow); border-radius: 2px; }
.index-group { margin-top: 6px; }
.index-row {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 4px; font-size: var(--fs-xs); color: var(--text-muted);
}
.index-codes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; }
.index-code {
  padding: 3px 0; cursor: pointer; text-align: center;
  border: 1px solid var(--border-soft); border-left-width: 2px;
  border-radius: var(--radius-sm); background: var(--bg-card-soft);
  color: var(--text-secondary); font-size: 10px;
  font-family: var(--font-mono); font-variant-numeric: tabular-nums;
}
.index-code:hover { color: var(--text-primary); border-color: var(--border-glow); }
.index-code.online { border-left-color: var(--accent-green); }
.index-code.alarm { border-left-color: var(--alert-critical); }
.index-code.degraded { border-left-color: var(--alert-warn); }
.index-code.offline { border-left-color: var(--status-offline); }
.index-code.maintenance { border-left-color: var(--accent-violet); }
.index-code.active {
  color: var(--accent-cyan); border-color: var(--accent-cyan);
  background: rgba(0, 229, 255, 0.1);
}
.index-empty { padding: 8px 4px; text-align: center; font-size: var(--fs-xs); color: var(--text-muted); }

.legend {
  position: absolute; left: 14px; bottom: 74px;
  display: flex; flex-direction: column; gap: 4px;
  padding: 8px 10px; border-radius: var(--radius-md);
  background: var(--bg-card-soft); border: 1px solid var(--border-soft);
  z-index: 3;
}
.legend-item { display: flex; align-items: center; gap: 6px; font-size: var(--fs-xs); color: var(--text-secondary); }

.node-strip {
  position: absolute; left: 12px; right: 336px; bottom: 12px;
  display: flex; gap: 6px; overflow-x: auto; padding: 6px;
  border-radius: var(--radius-lg); background: var(--bg-card-soft);
  border: 1px solid var(--border-soft);
  z-index: 3;
}
.node-strip::-webkit-scrollbar { height: 4px; }
.node-strip::-webkit-scrollbar-thumb { background: var(--border-glow); border-radius: 2px; }

.node-pill {
  flex: none; display: flex; flex-direction: column; gap: 1px;
  padding: 5px 10px; border-radius: var(--radius-md); cursor: pointer; text-align: left;
  background: var(--bg-card-soft); border: 1px solid var(--border-soft);
  color: var(--text-secondary);
}
.node-pill:hover { border-color: var(--border-glow); }
.node-pill.online { border-left: 2px solid var(--accent-green); }
.node-pill.alarm { border-left: 2px solid var(--alert-critical); }
.node-pill.degraded { border-left: 2px solid var(--alert-warn); }
.node-pill.offline { border-left: 2px solid var(--status-offline); }
.node-pill.maintenance { border-left: 2px solid var(--accent-violet); }
.node-pill.selected { background: var(--bg-card-hover); border-color: var(--accent-cyan); }
.pill-name { font-size: var(--fs-sm); color: var(--text-primary); }
.pill-meta { font-size: var(--fs-xs); color: var(--text-muted); }

.empty-hint { font-size: var(--fs-xs); color: var(--text-muted); padding: 6px; }

.stage-empty {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 10px; pointer-events: none;
  text-align: center; padding: 24px;
}
.empty-title { font-size: var(--fs-lg); color: var(--text-primary); }
.empty-desc { font-size: var(--fs-sm); color: var(--text-secondary); max-width: 420px; line-height: 1.7; }
.empty-desc code { color: var(--accent-cyan); background: rgba(0, 229, 255, 0.08); padding: 1px 4px; border-radius: 3px; }

@media (max-width: 1024px) {
  .node-strip { right: 12px; }
  .legend { display: none; }
  .slot-index { display: none; }
}
</style>
