<script setup lang="ts">
/** 中央孪生舞台：园区 → 货位 → 设备三级下钻 + 真实 GLB + 左右栏双向联动。 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  TwinLevelScene, type TwinNodeLite, type TwinStageKind, TWIN_STATUS_TEXT,
} from '@/core/TwinLevelScene'
import { useTwinStore } from '@/stores/twin'
import DevicePointPanel from '@/components/twin/DevicePointPanel.vue'
import type { TwinNode } from '@/api/twin'

const twin = useTwinStore()
const canvasRef = ref<HTMLCanvasElement | null>(null)
const wrapRef = ref<HTMLElement | null>(null)
const loadingModel = ref(false)
const isFullscreen = ref(false)

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

const tipText = computed(() => {
  if (stageKind.value === 'park') return '单击冷库进入库内 · 双击聚焦 · 拖拽旋转 · 滚轮缩放'
  const last = breadcrumb.value[breadcrumb.value.length - 1]
  if (last?.node_type === 'slot') return '点击设备查看点位 · Esc 返回货位层'
  return '单击货位查看设备 · 双击聚焦 · Esc 返回'
})

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

    // 下钻到货位后，直接把相机推到设备上，避免还停在整库视角
    const last = breadcrumb.value[breadcrumb.value.length - 1]
    if (last?.node_type === 'slot') {
      const device = levelNodes.value[0]
      if (device) scene.focusNode(device.node_key)
    }
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

  if (node.children.length) {
    twin.drill(node)
    return
  }
  const device = node.bindings[0]?.device_code
  if (device) twin.selectDevice(device)
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
}
</style>
