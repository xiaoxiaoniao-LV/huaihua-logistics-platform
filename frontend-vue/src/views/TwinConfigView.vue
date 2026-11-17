<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  bindTwinPoint, deleteTwinBinding, fetchDevicePoints, fetchSpaceTree, fetchTwinTree,
  saveTwinNode,
  type DevicePointOption, type SpaceNode, type TwinConfigNode,
} from '@/api/twin'
import { listDevices, type Device } from '@/api/devices'
import { apiError } from '@/utils/error'

const nodeTypeLabels: Record<string, string> = {
  site: '园区', building: '库区/建筑', floor: '楼层', room: '库房/房间', zone: '区域', rack: '货架/箱位', device: '设备位',
}
const statusLabels: Record<string, string> = {
  online: '在线', offline: '离线', degraded: '数据滞后', alarm: '告警', maintenance: '维护', unknown: '未接入',
}
const statusTag: Record<string, string> = {
  online: 'tag-green', offline: 'tag-red', degraded: 'tag-orange',
  alarm: 'tag-red', maintenance: 'tag-blue', unknown: 'tag-blue',
}
const bindingTypes = [
  { value: 'telemetry', label: '遥测值' },
  { value: 'status', label: '运行状态' },
  { value: 'anchor', label: '定位锚点' },
]

const loading = ref(false)
const loadError = ref('')
const actionError = ref('')
const actionOk = ref('')

const tree = ref<TwinConfigNode[]>([])
const spaces = ref<SpaceNode[]>([])
const devices = ref<Device[]>([])

function flattenNodes(nodes: TwinConfigNode[], depth = 0): { node: TwinConfigNode; depth: number }[] {
  const out: { node: TwinConfigNode; depth: number }[] = []
  for (const node of nodes) {
    out.push({ node, depth })
    if (node.children?.length) out.push(...flattenNodes(node.children, depth + 1))
  }
  return out
}

function flattenSpaces(nodes: SpaceNode[], depth = 0): { space: SpaceNode; depth: number }[] {
  const out: { space: SpaceNode; depth: number }[] = []
  for (const space of nodes) {
    out.push({ space, depth })
    if (space.children?.length) out.push(...flattenSpaces(space.children, depth + 1))
  }
  return out
}

const flatNodes = computed(() => flattenNodes(tree.value))
const flatSpaces = computed(() => flattenSpaces(spaces.value))

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [treeRes, spaceRes, devRes] = await Promise.all([
      fetchTwinTree(),
      fetchSpaceTree(),
      listDevices().catch(() => ({ data: [] as Device[] })),
    ])
    tree.value = treeRes.data.tree
    spaces.value = spaceRes.data.tree
    devices.value = devRes.data
    if (!selectedKey.value && flatNodes.value.length) selectNode(flatNodes.value[0].node)
  } catch (e) {
    loadError.value = apiError(e, '孪生配置加载失败')
  } finally {
    loading.value = false
  }
}

// ---------- 节点编辑 ----------
const selectedKey = ref('')
const isNew = ref(false)
const saving = ref(false)

const form = reactive({
  node_key: '',
  name: '',
  node_type: 'room',
  parent_id: '' as string | number,
  space_id: '' as string | number,
  model_ref: '',
  sort: 0,
  transform: '',
})

function selectNode(node: TwinConfigNode) {
  selectedKey.value = node.node_key
  isNew.value = false
  actionError.value = ''
  actionOk.value = ''
  form.node_key = node.node_key
  form.name = node.name
  form.node_type = node.node_type
  form.parent_id = node.parent_id ?? ''
  form.space_id = node.space_id ?? ''
  form.sort = node.sort ?? 0
  form.model_ref = node.model_ref || ''
  form.transform = node.transform ? JSON.stringify(node.transform, null, 2) : ''
  loadDevicePoints()
}

function startCreate() {
  selectedKey.value = ''
  isNew.value = true
  actionError.value = ''
  actionOk.value = ''
  form.node_key = ''
  form.name = ''
  form.node_type = 'room'
  form.parent_id = ''
  form.space_id = ''
  form.sort = 0
  form.model_ref = ''
  form.transform = ''
}

async function submitNode() {
  actionError.value = ''
  actionOk.value = ''
  if (!form.node_key.trim() || !form.name.trim()) {
    actionError.value = '请填写节点标识与名称'
    return
  }
  let transform: Record<string, unknown> | null = null
  if (form.transform.trim()) {
    try {
      transform = JSON.parse(form.transform)
    } catch {
      actionError.value = 'transform 不是合法 JSON'
      return
    }
  }
  saving.value = true
  try {
    const { data } = await saveTwinNode({
      node_key: form.node_key.trim(),
      name: form.name.trim(),
      node_type: form.node_type,
      parent_id: form.parent_id === '' ? null : Number(form.parent_id),
      space_id: form.space_id === '' ? null : Number(form.space_id),
      model_ref: form.model_ref || null,
      transform,
      sort: Number(form.sort) || 0,
    })
    actionOk.value = data.created ? `节点 ${data.node_key} 已创建` : `节点 ${data.node_key} 已更新`
    await load()
    const target = flatNodes.value.find((item) => item.node.node_key === data.node_key)?.node
    if (target) selectNode(target)
  } catch (e) {
    actionError.value = apiError(e, '节点保存失败')
  } finally {
    saving.value = false
  }
}

// ---------- 点位绑定 ----------
const bindForm = reactive({
  device_code: '',
  point_key: '',
  binding_type: 'telemetry',
})
const points = ref<DevicePointOption[]>([])
const pointLoading = ref(false)
const binding = ref(false)

async function loadDevicePoints() {
  points.value = []
  bindForm.point_key = ''
  if (!bindForm.device_code) return
  pointLoading.value = true
  try {
    const { data } = await fetchDevicePoints(bindForm.device_code)
    points.value = data.points
  } catch (e) {
    actionError.value = apiError(e, '点位字典加载失败')
  } finally {
    pointLoading.value = false
  }
}

async function addBinding() {
  if (!selectedKey.value) {
    actionError.value = '请先选择一个孪生节点'
    return
  }
  if (!bindForm.device_code || !bindForm.point_key) {
    actionError.value = '请选择设备与点位'
    return
  }
  binding.value = true
  actionError.value = ''
  actionOk.value = ''
  try {
    await bindTwinPoint({
      node_key: selectedKey.value,
      device_code: bindForm.device_code,
      point_key: bindForm.point_key,
      binding_type: bindForm.binding_type,
    })
    actionOk.value = '点位绑定已保存'
    await load()
    const target = flatNodes.value.find((item) => item.node.node_key === selectedKey.value)?.node
    if (target) selectNode(target)
  } catch (e) {
    actionError.value = apiError(e, '点位绑定失败')
  } finally {
    binding.value = false
  }
}

async function removeBinding(bindingId: number) {
  if (!window.confirm('确认解绑该点位？大屏将不再展示此测点。')) return
  actionError.value = ''
  try {
    await deleteTwinBinding(bindingId)
    actionOk.value = '已解绑'
    await load()
    const target = flatNodes.value.find((item) => item.node.node_key === selectedKey.value)?.node
    if (target) selectNode(target)
  } catch (e) {
    actionError.value = apiError(e, '解绑失败')
  }
}

const selectedNode = computed(() =>
  flatNodes.value.find((item) => item.node.node_key === selectedKey.value)?.node || null,
)

onMounted(load)
</script>

<template>
  <div class="page-scroll">
    <div class="toolbar">
      <span class="muted" style="font-size: 12px">
        孪生节点 {{ flatNodes.length }} 个 · 空间 {{ flatSpaces.length }} 个 · 设备 {{ devices.length }} 台
      </span>
      <span class="spacer"></span>
      <button class="btn btn-ghost btn-sm" :disabled="loading" @click="load">
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
      <button class="btn btn-sm" @click="startCreate">新建节点</button>
    </div>

    <div v-if="loadError" class="error-text">{{ loadError }}</div>

    <div class="twin-layout">
      <aside class="panel tree-panel">
        <div class="panel-head">
          <span class="panel-title">孪生节点树</span>
          <span class="muted" style="font-size: 12px">点击节点配置</span>
        </div>
        <div v-if="!flatNodes.length" class="empty">{{ loading ? '加载中…' : '暂无节点，点击「新建节点」' }}</div>
        <button
          v-for="item in flatNodes"
          :key="item.node.id"
          class="tree-row"
          :class="{ active: item.node.node_key === selectedKey }"
          :style="{ paddingLeft: `${12 + item.depth * 16}px` }"
          @click="selectNode(item.node)"
        >
          <div class="tree-main">
            <span class="tree-name">{{ item.node.name }}</span>
            <span class="tree-key">{{ item.node.node_key }}</span>
          </div>
          <div class="tree-side">
            <span class="tag" :class="statusTag[item.node.status] || 'tag-blue'">
              {{ statusLabels[item.node.status] || item.node.status }}
            </span>
            <span class="bind-count">{{ item.node.bindings.length }} 测点</span>
          </div>
        </button>
      </aside>

      <section class="panel detail-panel">
        <div class="panel-head">
          <span class="panel-title">{{ isNew ? '新建孪生节点' : selectedKey ? `节点 ${selectedKey}` : '节点详情' }}</span>
          <span v-if="selectedNode" class="muted" style="font-size: 12px">
            {{ nodeTypeLabels[selectedNode.node_type] || selectedNode.node_type }}
          </span>
        </div>

        <div v-if="!isNew && !selectedKey" class="empty">请在左侧选择节点，或新建节点</div>

        <div v-else class="detail-body">
          <div class="field-row">
            <div class="field">
              <label class="field-label">节点标识（node_key）</label>
              <input v-model="form.node_key" class="input" :disabled="!isNew" placeholder="如 room-cb3" />
            </div>
            <div class="field">
              <label class="field-label">节点名称</label>
              <input v-model="form.name" class="input" placeholder="如 冷链库房 C" />
            </div>
          </div>

          <div class="field-row">
            <div class="field">
              <label class="field-label">节点类型</label>
              <select v-model="form.node_type" class="select">
                <option v-for="(label, key) in nodeTypeLabels" :key="key" :value="key">{{ label }}</option>
              </select>
            </div>
            <div class="field">
              <label class="field-label">父节点</label>
              <select v-model="form.parent_id" class="select">
                <option value="">（根节点）</option>
                <option
                  v-for="item in flatNodes.filter((i) => i.node.node_key !== form.node_key)"
                  :key="item.node.id"
                  :value="item.node.id"
                >
                  {{ '　'.repeat(item.depth) }}{{ item.node.name }}（{{ item.node.node_key }}）
                </option>
              </select>
            </div>
          </div>

          <div class="field-row">
            <div class="field">
              <label class="field-label">关联空间</label>
              <select v-model="form.space_id" class="select">
                <option value="">（不关联）</option>
                <option
                  v-for="item in flatSpaces"
                  :key="item.space.id"
                  :value="item.space.id"
                >
                  {{ '　'.repeat(item.depth) }}{{ item.space.name }}（{{ item.space.kind }}）
                </option>
              </select>
            </div>
            <div class="field">
              <label class="field-label">排序</label>
              <input v-model.number="form.sort" class="input" type="number" min="0" max="9999" />
            </div>
          </div>

          <div class="field">
            <label class="field-label">模型引用（选填）</label>
            <input v-model="form.model_ref" class="input" placeholder="如 models/cold_room_cb3.glb" />
          </div>

          <div class="field">
            <label class="field-label">transform JSON（选填）</label>
            <textarea v-model="form.transform" class="textarea mono" placeholder='{"position":[0,0,0],"scale":1}' />
          </div>

          <div v-if="actionError" class="error-text">{{ actionError }}</div>
          <div v-if="actionOk" class="ok-text">{{ actionOk }}</div>

          <div class="actions">
            <button class="btn" :disabled="saving" @click="submitNode">
              {{ saving ? '保存中…' : isNew ? '创建节点' : '保存节点' }}
            </button>
          </div>

          <template v-if="selectedNode">
            <div class="section-title">点位绑定</div>
            <table class="table">
              <thead>
                <tr>
                  <th>设备</th>
                  <th>点位</th>
                  <th>类型</th>
                  <th>最新值</th>
                  <th>质量</th>
                  <th style="width: 90px">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="b in selectedNode.bindings" :key="b.id">
                  <td>{{ b.device_name || b.device_code }}</td>
                  <td>{{ b.name }} <span class="muted">({{ b.point_key }})</span></td>
                  <td class="muted">{{ bindingTypes.find((t) => t.value === b.binding_type)?.label || b.binding_type }}</td>
                  <td class="mono">{{ b.value ?? '-' }} {{ b.unit || '' }}</td>
                  <td class="muted">{{ b.quality }}</td>
                  <td>
                    <button class="btn btn-danger btn-sm" @click="removeBinding(b.id)">解绑</button>
                  </td>
                </tr>
                <tr v-if="!selectedNode.bindings.length">
                  <td colspan="6"><div class="empty">该节点还没有绑定测点</div></td>
                </tr>
              </tbody>
            </table>

            <div class="bind-form">
              <select v-model="bindForm.device_code" class="select" @change="loadDevicePoints">
                <option value="">选择设备</option>
                <option v-for="d in devices" :key="d.device_code" :value="d.device_code">
                  {{ d.device_code }} · {{ d.resource_name || d.device_type || '终端' }}（{{ d.status }}）
                </option>
              </select>
              <select v-model="bindForm.point_key" class="select" :disabled="pointLoading">
                <option value="">{{ pointLoading ? '点位加载中…' : '选择点位' }}</option>
                <option v-for="p in points" :key="p.id" :value="p.point_key">
                  {{ p.name }}（{{ p.point_key }}{{ p.unit ? ' / ' + p.unit : '' }}）
                </option>
              </select>
              <select v-model="bindForm.binding_type" class="select">
                <option v-for="t in bindingTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
              </select>
              <button class="btn" :disabled="binding" @click="addBinding">
                {{ binding ? '绑定中…' : '绑定点位' }}
              </button>
            </div>
          </template>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.twin-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 14px;
  align-items: start;
}
.tree-panel { padding-bottom: 8px; }
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle, rgba(120, 160, 220, 0.12));
}
.panel-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }

.tree-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: transparent;
  border: none;
  border-left: 2px solid transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s;
}
.tree-row:hover { background: rgba(0, 229, 255, 0.05); }
.tree-row.active {
  background: rgba(0, 229, 255, 0.1);
  border-left-color: var(--accent-cyan);
}
.tree-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.tree-name { font-size: 13px; color: var(--text-primary); }
.tree-key { font-size: 11px; color: var(--text-muted); font-family: 'Consolas', monospace; }
.tree-side { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
.bind-count { font-size: 11px; color: var(--text-muted); }

.detail-body { padding: 14px 16px 18px; }
.actions { display: flex; justify-content: flex-end; margin: 12px 0 4px; }
.section-title {
  margin: 18px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.bind-form {
  display: grid;
  grid-template-columns: 1.4fr 1.4fr 1fr auto;
  gap: 8px;
  margin-top: 10px;
}
.ok-text { color: var(--accent-green); font-size: var(--fs-sm); margin-top: 8px; }

@media (max-width: 1024px) {
  .twin-layout { grid-template-columns: 1fr; }
  .bind-form { grid-template-columns: 1fr; }
}
</style>
