<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  deleteAlertRule, listAlertRules, listAlerts, saveAlertRule,
  type AlertRule, type IoTAlert,
} from '@/api/iot'
import { listResources, type Resource } from '@/api/resources'
import { useAuthStore } from '@/stores/auth'
import { useIoTStore } from '@/stores/iot'
import AppModal from '@/components/common/AppModal.vue'
import { apiError } from '@/utils/error'

const auth = useAuthStore()
const iot = useIoTStore()

const tab = ref<'list' | 'rules'>('list')
const error = ref('')

// ---------- 告警列表 ----------
const levelLabels: Record<string, string> = { critical: '严重', warn: '警告', info: '提示' }
const levelTag: Record<string, string> = { critical: 'tag-red', warn: 'tag-orange', info: 'tag-blue' }
const typeLabels: Record<string, string> = {
  temperature_low: '温度偏低', temperature_high: '温度偏高', humidity_high: '湿度偏高',
}

const filter = ref<'active' | 'resolved' | 'all'>('active')
const filters: { key: typeof filter.value; label: string }[] = [
  { key: 'active', label: '待处理' },
  { key: 'resolved', label: '已解决' },
  { key: 'all', label: '全部' },
]

const rows = ref<IoTAlert[]>([])
const loading = ref(false)
const busy = ref<number | null>(null)
const activeCount = computed(() => rows.value.filter((a) => a.status === 'active').length)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await listAlerts({
      status: filter.value === 'all' ? undefined : filter.value,
      limit: 200,
    })
    rows.value = data.alerts
  } catch (e) {
    error.value = apiError(e, '加载告警失败')
  } finally {
    loading.value = false
  }
}

function switchFilter(next: typeof filter.value) {
  filter.value = next
  load()
}

async function resolve(a: IoTAlert) {
  if (!window.confirm(`确认告警「${a.message}」已处理？`)) return
  busy.value = a.id
  error.value = ''
  try {
    await iot.resolveAlert(a.id)
    if (filter.value === 'active') rows.value = rows.value.filter((x) => x.id !== a.id)
    else {
      const idx = rows.value.findIndex((x) => x.id === a.id)
      if (idx >= 0) rows.value[idx] = { ...rows.value[idx], status: 'resolved' }
    }
  } catch (e) {
    error.value = apiError(e, '处理失败')
  } finally {
    busy.value = null
  }
}

// ---------- 告警规则 ----------
const rules = ref<AlertRule[]>([])
const resources = ref<Resource[]>([])
const loadingRules = ref(false)
const rulesError = ref('')
const savingRule = ref(false)

const ruleForm = reactive({
  resource_id: 0,
  temp_min: -30,
  temp_max: -5,
  humidity_max: 90,
  enabled: true,
})
const showRuleForm = ref(false)
const addingRule = ref(false)

async function loadRules() {
  loadingRules.value = true
  try {
    const [ruleResp, resResp] = await Promise.all([
      listAlertRules(),
      listResources({ page_size: 200 }),
    ])
    rules.value = ruleResp.data
    resources.value = resResp.data.filter((r) => r.status !== 'pending')
  } finally {
    loadingRules.value = false
  }
}

function openRule(rule?: AlertRule) {
  addingRule.value = !rule
  rulesError.value = ''
  ruleForm.resource_id = rule ? rule.resource_id : 0
  ruleForm.temp_min = rule ? rule.temp_min : -30
  ruleForm.temp_max = rule ? rule.temp_max : -5
  ruleForm.humidity_max = rule ? rule.humidity_max : 90
  ruleForm.enabled = rule ? rule.enabled : true
  showRuleForm.value = true
}

async function saveRule() {
  rulesError.value = ''
  if (ruleForm.temp_min >= ruleForm.temp_max) {
    rulesError.value = '温度下限必须小于上限'
    return
  }
  savingRule.value = true
  try {
    await saveAlertRule(ruleForm.resource_id, {
      temp_min: ruleForm.temp_min,
      temp_max: ruleForm.temp_max,
      humidity_max: ruleForm.humidity_max,
      enabled: ruleForm.enabled,
    })
    showRuleForm.value = false
    await loadRules()
  } catch (e) {
    rulesError.value = apiError(e, '保存规则失败')
  } finally {
    savingRule.value = false
  }
}

async function removeRule(rule: AlertRule) {
  if (!window.confirm(`确认删除「${rule.resource_name}」的规则？将回退到全局默认。`)) return
  try {
    await deleteAlertRule(rule.resource_id)
    await loadRules()
  } catch (e) {
    rulesError.value = apiError(e, '删除失败')
  }
}

function switchTab(next: 'list' | 'rules') {
  tab.value = next
  error.value = ''
  if (next === 'list') load()
  else loadRules()
}

onMounted(async () => {
  if (!auth.user) await auth.fetchMe()
  await load()
})
</script>

<template>
  <div class="page-scroll">
    <div class="tabs">
      <button class="tab" :class="{ active: tab === 'list' }" @click="switchTab('list')">告警列表</button>
      <button class="tab" :class="{ active: tab === 'rules' }" @click="switchTab('rules')">告警规则</button>
    </div>

    <div v-if="error" class="error-text">{{ error }}</div>

    <!-- 告警列表 -->
    <template v-if="tab === 'list'">
      <div class="toolbar">
        <div class="filters">
          <button
            v-for="f in filters"
            :key="f.key"
            class="btn btn-sm"
            :class="filter === f.key ? '' : 'btn-ghost'"
            @click="switchFilter(f.key)"
          >
            {{ f.label }}
          </button>
        </div>
        <span class="muted" style="font-size: 12px">共 {{ rows.length }} 条，待处理 {{ activeCount }} 条</span>
        <span class="spacer"></span>
        <button class="btn btn-ghost btn-sm" :disabled="loading" @click="load">
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
      </div>

      <div class="panel">
        <table class="table">
          <thead>
            <tr>
              <th style="width: 140px">时间</th>
              <th>设备</th>
              <th>类型</th>
              <th>级别</th>
              <th>内容</th>
              <th>状态</th>
              <th style="width: 110px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in rows" :key="a.id">
              <td class="muted mono">{{ a.created_at.replace('T', ' ').slice(0, 19) }}</td>
              <td class="mono">{{ a.device_code || (a.device_id ? `#${a.device_id}` : '-') }}</td>
              <td class="muted">{{ typeLabels[a.type] || a.type }}</td>
              <td>
                <span class="tag" :class="levelTag[a.level] || 'tag-blue'">
                  {{ levelLabels[a.level] || a.level }}
                </span>
              </td>
              <td>{{ a.message }}</td>
              <td>
                <span class="tag" :class="a.status === 'active' ? 'tag-red' : 'tag-green'">
                  {{ a.status === 'active' ? '待处理' : '已解决' }}
                </span>
              </td>
              <td>
                <button
                  v-if="a.status === 'active' && auth.isLoggedIn"
                  class="btn btn-sm"
                  :disabled="busy === a.id"
                  @click="resolve(a)"
                >
                  标记已解决
                </button>
                <span v-else class="muted" style="font-size: 12px">-</span>
              </td>
            </tr>
            <tr v-if="!rows.length">
              <td colspan="7">
                <div class="empty">{{ loading ? '加载中…' : '暂无告警记录' }}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- 告警规则 -->
    <template v-else>
      <div class="toolbar">
        <span class="muted" style="font-size: 12px">
          生效顺序：资源级规则 → 全局默认 → 系统配置；关闭规则后该资源不再产生告警
        </span>
        <span class="spacer"></span>
        <button v-if="auth.isAdmin" class="btn btn-ghost btn-sm" :disabled="loadingRules" @click="loadRules">
          {{ loadingRules ? '刷新中…' : '刷新' }}
        </button>
        <button v-if="auth.isAdmin" class="btn btn-sm" @click="openRule()">新增资源规则</button>
      </div>

      <div v-if="rulesError" class="error-text">{{ rulesError }}</div>

      <div class="panel">
        <table class="table">
          <thead>
            <tr>
              <th>适用范围</th>
              <th>温度下限</th>
              <th>温度上限</th>
              <th>湿度上限</th>
              <th>状态</th>
              <th style="width: 150px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rules" :key="r.resource_id">
              <td>
                <span class="tag" :class="r.resource_id ? 'tag-blue' : 'tag-green'">
                  {{ r.resource_name || '全局默认' }}
                </span>
              </td>
              <td class="mono">{{ r.temp_min }}℃</td>
              <td class="mono">{{ r.temp_max }}℃</td>
              <td class="mono">{{ r.humidity_max }}%RH</td>
              <td>
                <span class="tag" :class="r.enabled ? 'tag-green' : 'tag-red'">
                  {{ r.enabled ? '已启用' : '已停用' }}
                </span>
              </td>
              <td>
                <template v-if="auth.isAdmin">
                  <button class="btn btn-ghost btn-sm" @click="openRule(r)">编辑</button>
                  <button
                    v-if="r.resource_id"
                    class="btn btn-danger btn-sm"
                    @click="removeRule(r)"
                  >
                    删除
                  </button>
                </template>
                <span v-else class="muted" style="font-size: 12px">只读</span>
              </td>
            </tr>
            <tr v-if="!rules.length">
              <td colspan="6"><div class="empty">{{ loadingRules ? '加载中…' : '暂无规则' }}</div></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <AppModal v-if="showRuleForm" :title="addingRule ? '新增资源规则' : '编辑告警规则'" @close="showRuleForm = false">
      <div class="field">
        <label class="field-label">适用范围</label>
        <select v-model.number="ruleForm.resource_id" class="select" :disabled="!addingRule">
          <option :value="0">全局默认</option>
          <option v-for="r in resources" :key="r.id" :value="r.id">{{ r.name }}</option>
        </select>
      </div>
      <div class="field-row">
        <div class="field">
          <label class="field-label">温度下限（℃）</label>
          <input v-model.number="ruleForm.temp_min" class="input" type="number" step="0.5" />
        </div>
        <div class="field">
          <label class="field-label">温度上限（℃）</label>
          <input v-model.number="ruleForm.temp_max" class="input" type="number" step="0.5" />
        </div>
      </div>
      <div class="field-row">
        <div class="field">
          <label class="field-label">湿度上限（%RH）</label>
          <input v-model.number="ruleForm.humidity_max" class="input" type="number" step="1" />
        </div>
        <div class="field">
          <label class="field-label">是否启用</label>
          <select v-model="ruleForm.enabled" class="select">
            <option :value="true">启用</option>
            <option :value="false">停用</option>
          </select>
        </div>
      </div>
      <div class="error-text">{{ rulesError }}</div>

      <template #footer>
        <button class="btn btn-ghost" @click="showRuleForm = false">取消</button>
        <button class="btn" :disabled="savingRule" @click="saveRule">
          {{ savingRule ? '保存中…' : '保存' }}
        </button>
      </template>
    </AppModal>
  </div>
</template>

<style scoped>
.filters { display: flex; gap: 6px; }
.tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border-glow);
}
.tab {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 13px;
  padding: 8px 16px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}
.tab.active { color: var(--accent-cyan); border-bottom-color: var(--accent-cyan); }
</style>
