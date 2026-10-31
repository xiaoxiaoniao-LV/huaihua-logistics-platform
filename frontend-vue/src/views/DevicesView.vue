<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  autoBindDevices, createDevice, deleteDevice, listDevices, updateDevice, type Device,
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
  warehouse: '仓库', cold_box: '冷链箱', vehicle: '运力', equipment: '设备',
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

onMounted(load)
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
            <th>最新温度</th>
            <th>最新湿度</th>
            <th>最后上报</th>
            <th style="width: 190px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in list" :key="d.id">
            <td class="mono">{{ d.device_code }}</td>
            <td class="muted">{{ d.device_type || '-' }}</td>
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
            <td colspan="8">
              <div class="empty">{{ loading ? '加载中…' : '暂无设备，可点击右上角「新增设备」' }}</div>
            </td>
          </tr>
        </tbody>
      </table>
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
  </div>
</template>

<style scoped>
.filters { display: flex; gap: 6px; }
</style>
