﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  autoBindDevices, createDevice, createOtaJob, deleteDevice, getOtaBatch, importDevices,
  listDevices, listOtaTasks, promoteOtaBatch, rollbackOtaBatch, updateDevice,
  type Device, type ImportResult, type OtaBatch, type OtaTask,
} from '@/api/devices'
import { listResources, type Resource } from '@/api/resources'
import { useAuthStore } from '@/stores/auth'
import AppModal from '@/components/common/AppModal.vue'
import { apiError } from '@/utils/error'

const auth = useAuthStore()

const devices = ref<Device[]>([])
const resources = ref<Resource[]>([])
const loading = ref(false)
const error = ref('')
const busy = ref<number | null>(null)
const filter = ref<'all' | 'online' | 'offline'>('all')

const filters: { key: typeof filter.value; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'online', label: '在线' },
  { key: 'offline', label: '离线' },
]

const typeLabels: Record<string, string> = {
  warehouse: '冷库', cold_box: '冷链箱位', vehicle: '冷藏运输', equipment: '温控设备',
}
const deviceTypeLabels: Record<string, string> = {
  dht22: '温湿度传感器', temp_humidity: '温湿度传感器',
  gps: 'GPS 定位', gps_temp: 'GPS + 温湿度',
  esp32: 'ESP32 网关',
}

const list = computed(() =>
  filter.value === 'all' ? devices.value : devices.value.filter((d) => d.status === filter.value),
)
const onlineCount = computed(() => devices.value.filter((d) => d.status === 'online').length)
const unboundCount = computed(() => devices.value.filter((d) => !d.resource_id).length)

const myResourceIds = computed(
  () => new Set(resources.value.filter((r) => r.user_id === auth.user?.id).map((r) => r.id)),
)

function canManage(d: Device) {
  return auth.isAdmin || (d.resource_id > 0 && myResourceIds.value.has(d.resource_id))
}

function fmtTime(v?: string | null) {
  if (!v) return '-'
  return v.replace('T', ' ').slice(0, 19)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [devResp, resResp] = await Promise.all([
      listDevices(),
      listResources({ page_size: 200 }),
    ])
    devices.value = devResp.data
    resources.value = resResp.data.filter((r) => r.status !== 'pending')
  } catch (e) {
    error.value = apiError(e, '加载设备失败')
  } finally {
    loading.value = false
  }
}

// ---------- 新增 / 编辑 ----------
const showForm = ref(false)
const editing = ref<Device | null>(null)
const submitting = ref(false)
const formError = ref('')
const form = reactive({ device_code: '', device_type: 'dht22', resource_id: 0 })

function openCreate() {
  editing.value = null
  formError.value = ''
  form.device_code = ''
  form.device_type = 'dht22'
  form.resource_id = 0
  showForm.value = true
}

function openEdit(d: Device) {
  editing.value = d
  formError.value = ''
  form.device_code = d.device_code
  form.device_type = d.device_type || 'dht22'
  form.resource_id = d.resource_id || 0
  showForm.value = true
}

async function submitForm() {
  formError.value = ''
  if (!editing.value && !form.device_code.trim()) {
    formError.value = '请填写设备编码'
    return
  }
  submitting.value = true
  try {
    if (editing.value) {
      await updateDevice(editing.value.id, {
        device_type: form.device_type || undefined,
        resource_id: form.resource_id || 0,
      })
    } else {
      await createDevice({
        device_code: form.device_code.trim(),
        device_type: form.device_type || undefined,
        resource_id: form.resource_id || 0,
      })
    }
    showForm.value = false
    await load()
  } catch (e) {
    formError.value = apiError(e, '保存失败')
  } finally {
    submitting.value = false
  }
}

// ---------- 绑定 / 删除 / 自动绑定 ----------
async function bindTo(d: Device, resourceId: number) {
  busy.value = d.id
  error.value = ''
  try {
    await updateDevice(d.id, { resource_id: resourceId })
    await load()
  } catch (e) {
    error.value = apiError(e, '绑定失败')
  } finally {
    busy.value = null
  }
}

async function remove(d: Device) {
  if (!window.confirm(`确认删除设备「${d.device_code}」？`)) return
  busy.value = d.id
  error.value = ''
  try {
    await deleteDevice(d.id)
    await load()
  } catch (e) {
    error.value = apiError(e, '删除失败')
  } finally {
    busy.value = null
  }
}

const binding = ref(false)
async function runAutoBind() {
  binding.value = true
  error.value = ''
  try {
    const { data } = await autoBindDevices()
    window.alert(data.detail)
    await load()
  } catch (e) {
    error.value = apiError(e, '自动绑定失败')
  } finally {
    binding.value = false
  }
}

onMounted(() => {
  load()
  loadOtaTasks()
})

// ---------- 批量导入 ----------
const showImport = ref(false)
const importFile = ref<File | null>(null)
const importing = ref(false)
const importResult = ref<ImportResult | null>(null)
const importError = ref('')

function openImport() {
  importFile.value = null
  importResult.value = null
  importError.value = ''
  showImport.value = true
}

function onFileChange(e: Event) {
  importFile.value = (e.target as HTMLInputElement).files?.[0] ?? null
}

async function submitImport() {
  importError.value = ''
  if (!importFile.value) {
    importError.value = '请选择 CSV 文件'
    return
  }
  importing.value = true
  try {
    const { data } = await importDevices(importFile.value)
    importResult.value = data
    await load()
  } catch (e) {
    importError.value = apiError(e, '导入失败')
  } finally {
    importing.value = false
  }
}

// ---------- 固件 OTA ----------
const otaTasks = ref<OtaTask[]>([])
const showOta = ref(false)
const otaVersion = ref('1.1.0')
const otaSelected = ref<number[]>([])
const otaPercent = ref(100)
const otaSubmitting = ref(false)
const otaError = ref('')
const otaResult = ref('')
const otaBatch = ref<OtaBatch | null>(null)
const otaBatchBusy = ref(false)

const otaStatusLabels: Record<string, string> = {
  pending: '待下发', running: '下发中', success: '成功', failed: '失败',
}
const otaStageLabels: Record<string, string> = {
  canary: '灰度', full: '全量', rollback: '回滚',
}
const otaBatchStatusLabels: Record<string, string> = {
  running: '进行中', done: '已完成', failed: '有失败', rolled_back: '已回滚',
}

async function loadOtaBatch(batchId: string) {
  try {
    const { data } = await getOtaBatch(batchId)
    otaBatch.value = data
  } catch {
    // 批次信息属于辅助信息，失败不阻断主流程
  }
}

async function loadOtaTasks() {
  try {
    const { data } = await listOtaTasks(20)
    otaTasks.value = data
    const latest = data.find((t) => t.batch_id)
    if (latest?.batch_id) await loadOtaBatch(latest.batch_id)
  } catch {
    // 升级任务列表属于辅助信息，失败不阻断设备列表
  }
}

function openOta() {
  otaVersion.value = '1.1.0'
  otaSelected.value = devices.value.filter((d) => d.status === 'online').map((d) => d.id)
  otaPercent.value = 100
  otaError.value = ''
  otaResult.value = ''
  showOta.value = true
}

function toggleAllOta() {
  const onlineIds = devices.value.filter((d) => d.status === 'online').map((d) => d.id)
  otaSelected.value = onlineIds.every((id) => otaSelected.value.includes(id)) ? [] : onlineIds
}

async function submitOta() {
  otaError.value = ''
  otaResult.value = ''
  const target = otaVersion.value.trim()
  if (!target) {
    otaError.value = '请填写目标版本'
    return
  }
  if (!otaSelected.value.length) {
    otaError.value = '请至少选择一台设备'
    return
  }
  otaSubmitting.value = true
  try {
    const percent = Math.min(100, Math.max(1, Number(otaPercent.value) || 100))
    const { data } = await createOtaJob({
      target_version: target,
      device_ids: otaSelected.value,
      rollout_percent: percent,
    })
    otaResult.value = data.length
      ? `已创建 ${data.length} 个升级任务（${percent < 100 ? `灰度 ${percent}%` : '全量'}），等待设备回执`
      : '所选设备已是目标版本，无需升级'
    const batchId = data.find((t) => t.batch_id)?.batch_id
    if (batchId) await loadOtaBatch(batchId)
    await Promise.all([load(), loadOtaTasks()])
  } catch (e) {
    otaError.value = apiError(e, '下发失败')
  } finally {
    otaSubmitting.value = false
  }
}

async function promoteOta() {
  if (!otaBatch.value) return
  otaBatchBusy.value = true
  otaError.value = ''
  try {
    const { data } = await promoteOtaBatch(otaBatch.value.batch_id)
    otaBatch.value = data
    otaResult.value = '已续发为全量，剩余设备将陆续收到升级指令'
    await Promise.all([load(), loadOtaTasks()])
  } catch (e) {
    otaError.value = apiError(e, '续发失败')
  } finally {
    otaBatchBusy.value = false
  }
}

async function rollbackOta() {
  if (!otaBatch.value) return
  if (!window.confirm(`确认回滚批次 ${otaBatch.value.batch_id} 到升级前版本？`)) return
  otaBatchBusy.value = true
  otaError.value = ''
  try {
    const { data } = await rollbackOtaBatch(otaBatch.value.batch_id)
    otaBatch.value = data
    otaResult.value = '已创建回滚批次，等待设备回执'
    await Promise.all([load(), loadOtaTasks()])
  } catch (e) {
    otaError.value = apiError(e, '回滚失败')
  } finally {
    otaBatchBusy.value = false
  }
}
</script>

<template>
  <div class="page-scroll">
    <div class="toolbar">
      <div class="filters">
        <button
          v-for="f in filters"
          :key="f.key"
          class="btn btn-sm"
          :class="filter === f.key ? '' : 'btn-ghost'"
          @click="filter = f.key"
        >
          {{ f.label }}
        </button>
      </div>
      <span class="muted" style="font-size: 12px">
        共 {{ devices.length }} 台，在线 {{ onlineCount }} 台，未绑定 {{ unboundCount }} 台
      </span>
      <span class="spacer"></span>
      <button v-if="auth.isAdmin" class="btn btn-ghost btn-sm" @click="openImport">批量导入</button>
      <button v-if="auth.isAdmin" class="btn btn-ghost btn-sm" @click="openOta">固件升级</button>
      <button v-if="auth.isAdmin" class="btn btn-ghost btn-sm" :disabled="binding" @click="runAutoBind">
        {{ binding ? '绑定中…' : '自动绑定' }}
      </button>
      <button class="btn btn-ghost btn-sm" :disabled="loading" @click="load">
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
      <button class="btn btn-sm" @click="openCreate">新增设备</button>
    </div>

    <div v-if="error" class="error-text">{{ error }}</div>

    <div class="panel">
      <table class="table">
        <thead>
          <tr>
            <th>设备编码</th>
            <th>类型</th>
            <th>绑定资源</th>
            <th>状态</th>
            <th>固件</th>
            <th>最新温度</th>
            <th>最新湿度</th>
            <th>最后上报</th>
            <th style="width: 190px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in list" :key="d.id">
            <td class="mono">{{ d.device_code }}</td>
            <td class="muted">{{ (d.device_type && deviceTypeLabels[d.device_type]) || d.device_type || '-' }}</td>
            <td>
              <select
                v-if="canManage(d)"
                class="select"
                style="width: 180px"
                :value="d.resource_id || 0"
                :disabled="busy === d.id"
                @change="bindTo(d, Number(($event.target as HTMLSelectElement).value))"
              >
                <option :value="0">未绑定</option>
                <option v-for="r in resources" :key="r.id" :value="r.id">
                  {{ r.name }}（{{ typeLabels[r.type] || r.type }}）
                </option>
              </select>
              <span v-else class="muted">{{ d.resource_name || '未绑定' }}</span>
            </td>
            <td>
              <span class="tag" :class="d.status === 'online' ? 'tag-green' : 'tag-red'">
                {{ d.status === 'online' ? '在线' : '离线' }}
              </span>
            </td>
            <td class="mono" style="font-size: 12px">{{ d.firmware_version || '1.0.0' }}</td>
            <td class="mono" style="color: var(--accent-orange)">
              {{ d.last_temperature != null ? `${d.last_temperature.toFixed(1)}℃` : '-' }}
            </td>
            <td class="mono">{{ d.last_humidity != null ? `${d.last_humidity.toFixed(1)}%` : '-' }}</td>
            <td class="muted mono" style="font-size: 12px">{{ fmtTime(d.last_seen) }}</td>
            <td>
              <template v-if="canManage(d)">
                <button class="btn btn-ghost btn-sm" @click="openEdit(d)">编辑</button>
                <button class="btn btn-danger btn-sm" :disabled="busy === d.id" @click="remove(d)">删除</button>
              </template>
              <span v-else class="muted" style="font-size: 12px">-</span>
            </td>
          </tr>
          <tr v-if="!list.length">
            <td colspan="9">
              <div class="empty">{{ loading ? '加载中…' : '暂无设备，可点击右上角「新增设备」' }}</div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="otaTasks.length" class="panel" style="margin-top: 12px">
      <div class="panel-title">最近升级任务</div>
      <div class="panel-body">
        <div v-if="otaBatch" class="ota-batch">
          <div class="ota-batch-head">
            <span class="mono">
              {{ otaStageLabels[otaBatch.stage] || otaBatch.stage }} · v{{ otaBatch.target_version }}
              <span v-if="otaBatch.stage === 'canary'" class="muted">（{{ otaBatch.rollout_percent }}%）</span>
            </span>
            <span
              class="tag"
              :class="{
                'tag-green': otaBatch.status === 'done',
                'tag-red': otaBatch.status === 'failed' || otaBatch.status === 'rolled_back',
                'tag-blue': otaBatch.status === 'running',
              }"
            >
              {{ otaBatchStatusLabels[otaBatch.status] || otaBatch.status }}
            </span>
          </div>
          <div class="muted" style="font-size: 12px">
            共 {{ otaBatch.total }} 台：成功 {{ otaBatch.success }} · 失败 {{ otaBatch.failed }} ·
            下发中 {{ otaBatch.running }} · 待下发 {{ otaBatch.pending }}
            <span class="mono" style="font-size: 11px; margin-left: 6px">{{ otaBatch.batch_id.slice(0, 8) }}</span>
          </div>
          <div class="ota-batch-actions">
            <button
              v-if="otaBatch.stage === 'canary' && otaBatch.status === 'running'"
              class="btn btn-sm"
              :disabled="otaBatchBusy"
              @click="promoteOta"
            >
              续发全量
            </button>
            <button
              v-if="otaBatch.status !== 'rolled_back' && otaBatch.stage !== 'rollback'"
              class="btn btn-ghost btn-sm"
              :disabled="otaBatchBusy"
              @click="rollbackOta"
            >
              回滚批次
            </button>
          </div>
        </div>
        <table class="table">
          <thead>
            <tr>
              <th>设备</th>
              <th>版本变化</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>完成时间</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in otaTasks" :key="t.id">
              <td class="mono">{{ t.device_code || `#${t.device_id}` }}</td>
              <td class="mono">{{ t.from_version || '-' }} → {{ t.target_version }}</td>
              <td>
                <span
                  class="tag"
                  :class="{
                    'tag-green': t.status === 'success',
                    'tag-red': t.status === 'failed',
                    'tag-blue': t.status === 'running' || t.status === 'pending',
                  }"
                >
                  {{ otaStatusLabels[t.status] || t.status }}
                </span>
              </td>
              <td class="muted mono" style="font-size: 12px">{{ fmtTime(t.created_at) }}</td>
              <td class="muted mono" style="font-size: 12px">{{ fmtTime(t.finished_at) }}</td>
              <td class="muted" style="font-size: 12px">{{ t.message || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <AppModal v-if="showForm" :title="editing ? '编辑设备' : '新增设备'" @close="showForm = false">
      <div class="field">
        <label class="field-label">设备编码</label>
        <input
          v-model="form.device_code"
          class="input"
          :disabled="!!editing"
          placeholder="如：CW-01（与上报时 device_code 一致）"
        />
      </div>
      <div class="field-row">
        <div class="field">
          <label class="field-label">设备类型</label>
          <select v-model="form.device_type" class="select">
            <option value="dht22">温湿度传感器 DHT22</option>
            <option value="esp32">ESP32 网关</option>
            <option value="gps">GPS 定位</option>
          </select>
        </div>
        <div class="field">
          <label class="field-label">绑定资源</label>
          <select v-model.number="form.resource_id" class="select">
            <option :value="0">暂不绑定</option>
            <option v-for="r in resources" :key="r.id" :value="r.id">{{ r.name }}</option>
          </select>
        </div>
      </div>
      <div class="field-hint">设备上报的 device_code 必须与此处一致，才会关联到资源并触发告警。</div>
      <div class="error-text">{{ formError }}</div>

      <template #footer>
        <button class="btn btn-ghost" @click="showForm = false">取消</button>
        <button class="btn" :disabled="submitting" @click="submitForm">
          {{ submitting ? '保存中…' : '保存' }}
        </button>
      </template>
    </AppModal>

    <AppModal v-if="showImport" title="批量导入设备" @close="showImport = false">
      <div class="field">
        <label class="field-label">CSV 文件</label>
        <input type="file" accept=".csv,text/csv" class="input" @change="onFileChange" />
      </div>
      <div class="field-hint">
        表头：device_code,device_type,resource_id,firmware_version；仅 device_code 必填，单次最多 500 行。
        编码已存在的设备会自动跳过。
      </div>
      <div v-if="importResult" class="import-result">
        <div>
          新增 <b>{{ importResult.created }}</b> 台，跳过 <b>{{ importResult.skipped }}</b> 台，
          失败 <b>{{ importResult.failed }}</b> 行
        </div>
        <ul v-if="importResult.errors.length" class="err-list">
          <li v-for="e in importResult.errors" :key="e.row">
            第 {{ e.row }} 行<span v-if="e.device_code">（{{ e.device_code }}）</span>：{{ e.reason }}
          </li>
        </ul>
      </div>
      <div class="error-text">{{ importError }}</div>

      <template #footer>
        <button class="btn btn-ghost" @click="showImport = false">关闭</button>
        <button class="btn" :disabled="importing" @click="submitImport">
          {{ importing ? '导入中…' : '开始导入' }}
        </button>
      </template>
    </AppModal>

    <AppModal v-if="showOta" title="固件批量升级" @close="showOta = false">
      <div class="field">
        <label class="field-label">目标版本</label>
        <input v-model="otaVersion" class="input" placeholder="如：1.1.0" />
      </div>
      <div class="field">
        <label class="field-label">灰度比例（%）</label>
        <input
          v-model.number="otaPercent"
          class="input"
          type="number"
          min="1"
          max="100"
          step="1"
        />
      </div>
      <div class="field-hint">
        平台通过 MQTT 向 iot/{device_code}/cmd 下发 OTA 指令，设备回执成功后固件版本自动更新。
        已是目标版本的设备会被跳过。灰度比例小于 100 时按批次号稳定抽样，先升级一部分设备，
        确认无异常后可在批次面板一键续发全量；出问题可整批回滚。
      </div>
      <div class="ota-pick">
        <div class="ota-pick-head">
          <span class="muted">已选 {{ otaSelected.length }} / {{ devices.length }} 台</span>
          <button class="btn btn-ghost btn-sm" @click="toggleAllOta">全选在线</button>
        </div>
        <div class="ota-list">
          <label v-for="d in devices" :key="d.id" class="ota-item">
            <input v-model="otaSelected" type="checkbox" :value="d.id" />
            <span class="mono">{{ d.device_code }}</span>
            <span class="muted mono">v{{ d.firmware_version || '1.0.0' }}</span>
            <span class="tag" :class="d.status === 'online' ? 'tag-green' : 'tag-red'">
              {{ d.status === 'online' ? '在线' : '离线' }}
            </span>
          </label>
          <div v-if="!devices.length" class="empty">暂无可升级设备</div>
        </div>
      </div>
      <div v-if="otaResult" class="import-result">{{ otaResult }}</div>
      <div class="error-text">{{ otaError }}</div>

      <template #footer>
        <button class="btn btn-ghost" @click="showOta = false">关闭</button>
        <button class="btn" :disabled="otaSubmitting" @click="submitOta">
          {{ otaSubmitting ? '下发中…' : '下发升级' }}
        </button>
      </template>
    </AppModal>
  </div>
</template>

<style scoped>
.filters { display: flex; gap: 6px; }
.import-result {
  margin-top: 10px; padding: 8px 10px; font-size: 12px;
  border: 1px solid var(--border-glow); border-radius: 4px;
  background: rgba(0, 229, 255, 0.04);
}
.err-list {
  margin: 6px 0 0; padding-left: 18px; max-height: 140px; overflow: auto;
  color: var(--accent-orange); font-size: 11px;
}
.ota-pick { margin-top: 10px; }
.ota-pick-head {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 12px; margin-bottom: 6px;
}
.ota-list {
  max-height: 220px; overflow: auto;
  border: 1px solid var(--border-glow); border-radius: 4px;
}
.ota-item {
  display: flex; align-items: center; gap: 10px;
  padding: 5px 10px; font-size: 12px; cursor: pointer;
  border-bottom: 1px solid rgba(64, 158, 255, 0.08);
}
.ota-item:last-child { border-bottom: none; }
.ota-item:hover { background: rgba(0, 229, 255, 0.06); }
.ota-item span:nth-of-type(1) { flex: 1; }
.ota-batch {
  margin-bottom: 10px; padding: 8px 10px;
  border: 1px solid var(--border-glow); border-radius: 4px;
  background: rgba(0, 229, 255, 0.03);
}
.ota-batch-head {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 12px; margin-bottom: 4px;
}
.ota-batch-actions { display: flex; gap: 6px; margin-top: 8px; }
</style>
