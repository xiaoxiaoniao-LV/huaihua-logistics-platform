<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listResources, reviewResource, type Resource } from '@/api/resources'
import { adminUpdateUser, listUsers, type AdminUser } from '@/api/users'
import { listAuditLogs, type AuditLogItem } from '@/api/audit'
import { useAuthStore } from '@/stores/auth'
import AppModal from '@/components/common/AppModal.vue'
import { apiError } from '@/utils/error'

const auth = useAuthStore()

const tab = ref<'review' | 'users' | 'audit'>('review')
const error = ref('')
const busy = ref<number | null>(null)

const typeLabels: Record<string, string> = {
  warehouse: '仓库', cold_box: '冷链箱', vehicle: '运力', equipment: '设备',
}
const roleLabels: Record<string, string> = {
  supplier: '供给方', demander: '需求方', admin: '管理员',
}
const actionLabels: Record<string, string> = {
  login: '登录', change_password: '修改密码', resource_review: '资源审核',
  user_update: '用户变更', alert_resolve: '告警处理',
}

// ---------- 资源审核 ----------
const pending = ref<Resource[]>([])
const loadingPending = ref(false)

async function loadPending() {
  loadingPending.value = true
  try {
    const { data } = await listResources({ status: 'pending', page_size: 200 })
    pending.value = data
  } finally {
    loadingPending.value = false
  }
}

const rejecting = ref<Resource | null>(null)
const rejectReason = ref('')

async function approve(r: Resource) {
  error.value = ''
  busy.value = r.id
  try {
    await reviewResource(r.id, true)
    await loadPending()
  } catch (e) {
    error.value = apiError(e, '审核失败')
  } finally {
    busy.value = null
  }
}

function openReject(r: Resource) {
  rejecting.value = r
  rejectReason.value = ''
  error.value = ''
}

async function confirmReject() {
  if (!rejecting.value) return
  busy.value = rejecting.value.id
  try {
    await reviewResource(rejecting.value.id, false, rejectReason.value || undefined)
    rejecting.value = null
    await loadPending()
  } catch (e) {
    error.value = apiError(e, '驳回落败')
  } finally {
    busy.value = null
  }
}

// ---------- 用户管理 ----------
const users = ref<AdminUser[]>([])
const loadingUsers = ref(false)
const keyword = ref('')

const filteredUsers = computed(() => {
  const kw = keyword.value.trim()
  if (!kw) return users.value
  return users.value.filter((u) => u.username.includes(kw) || (u.company_name || '').includes(kw))
})

async function loadUsers() {
  loadingUsers.value = true
  try {
    const { data } = await listUsers()
    users.value = data
  } finally {
    loadingUsers.value = false
  }
}

function publisherName(userId: number) {
  const u = users.value.find((x) => x.id === userId)
  return u ? u.company_name || u.username : `#${userId}`
}

async function patchUser(u: AdminUser, payload: { role?: string; is_active?: boolean }) {
  error.value = ''
  busy.value = u.id
  try {
    const { data } = await adminUpdateUser(u.id, payload)
    const idx = users.value.findIndex((x) => x.id === u.id)
    if (idx >= 0) users.value[idx] = data
  } catch (e) {
    error.value = apiError(e, '操作失败')
  } finally {
    busy.value = null
  }
}

function switchTab(next: 'review' | 'users' | 'audit') {
  tab.value = next
  error.value = ''
  if (next === 'review') loadPending()
  else if (next === 'users') loadUsers()
  else loadAuditLogs()
}

// ---------- 审计日志 ----------
const auditLogs = ref<AuditLogItem[]>([])
const loadingAudit = ref(false)
const auditAction = ref('')
const auditTotal = ref(0)

async function loadAuditLogs() {
  loadingAudit.value = true
  try {
    const resp = await listAuditLogs({ action: auditAction.value || undefined, page_size: 100 })
    auditLogs.value = resp.data
    auditTotal.value = Number(resp.headers['x-total-count'] ?? resp.data.length)
  } catch (e) {
    error.value = apiError(e, '加载审计日志失败')
  } finally {
    loadingAudit.value = false
  }
}

function fmtTime(v: string) {
  return v.replace('T', ' ').slice(0, 19)
}

onMounted(async () => {
  if (!auth.user) await auth.fetchMe()
  if (auth.isAdmin) await Promise.all([loadPending(), loadUsers()])
})
</script>

<template>
  <div class="page-scroll">
    <div v-if="!auth.isAdmin" class="panel">
      <div class="empty">该页面仅管理员可访问</div>
    </div>

    <template v-else>
      <div class="tabs">
        <button class="tab" :class="{ active: tab === 'review' }" @click="switchTab('review')">
          资源审核
          <span v-if="pending.length" class="badge">{{ pending.length }}</span>
        </button>
        <button class="tab" :class="{ active: tab === 'users' }" @click="switchTab('users')">用户管理</button>
        <button class="tab" :class="{ active: tab === 'audit' }" @click="switchTab('audit')">审计日志</button>
      </div>

      <div v-if="error" class="error-text">{{ error }}</div>

      <!-- 资源审核 -->
      <div v-if="tab === 'review'" class="panel">
        <table class="table">
          <thead>
            <tr>
              <th>资源名称</th>
              <th>类型</th>
              <th>发布方</th>
              <th>位置</th>
              <th>价格</th>
              <th style="width: 170px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in pending" :key="r.id">
              <td>{{ r.name }}</td>
              <td class="muted">{{ typeLabels[r.type] || r.type }}</td>
              <td class="muted">{{ publisherName(r.user_id) }}</td>
              <td class="muted">{{ r.location || '-' }}</td>
              <td class="mono" style="color: var(--accent-orange)">
                {{ r.price != null ? `¥${r.price}/${r.price_unit || '天'}` : '-' }}
              </td>
              <td>
                <button class="btn btn-sm" :disabled="busy === r.id" @click="approve(r)">通过</button>
                <button class="btn btn-danger btn-sm" :disabled="busy === r.id" @click="openReject(r)">
                  驳回
                </button>
              </td>
            </tr>
            <tr v-if="!pending.length">
              <td colspan="6">
                <div class="empty">{{ loadingPending ? '加载中…' : '暂无待审核资源' }}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 用户管理 -->
      <div v-else-if="tab === 'users'">
        <div class="toolbar">
          <input v-model="keyword" class="input" style="width: 240px" placeholder="搜索用户名 / 企业名" />
          <span class="muted" style="font-size: 12px">共 {{ filteredUsers.length }} 个用户</span>
          <span class="spacer"></span>
          <button class="btn btn-ghost btn-sm" :disabled="loadingUsers" @click="loadUsers">
            {{ loadingUsers ? '刷新中…' : '刷新' }}
          </button>
        </div>

        <div class="panel">
          <table class="table">
            <thead>
              <tr>
                <th>用户名</th>
                <th>企业</th>
                <th>角色</th>
                <th>信用分</th>
                <th>状态</th>
                <th style="width: 200px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in filteredUsers" :key="u.id">
                <td class="mono">{{ u.username }}</td>
                <td class="muted">{{ u.company_name || '-' }}</td>
                <td>
                  <select
                    class="select"
                    style="width: 110px"
                    :value="u.role"
                    :disabled="busy === u.id || u.id === auth.user?.id"
                    @change="patchUser(u, { role: ($event.target as HTMLSelectElement).value })"
                  >
                    <option v-for="(label, key) in roleLabels" :key="key" :value="key">{{ label }}</option>
                  </select>
                </td>
                <td class="mono" style="color: var(--accent-orange)">{{ u.credit_score }}</td>
                <td>
                  <span class="tag" :class="u.is_active ? 'tag-green' : 'tag-red'">
                    {{ u.is_active ? '正常' : '已禁用' }}
                  </span>
                </td>
                <td>
                  <button
                    v-if="u.id !== auth.user?.id"
                    class="btn btn-sm"
                    :class="u.is_active ? 'btn-danger' : ''"
                    :disabled="busy === u.id"
                    @click="patchUser(u, { is_active: !u.is_active })"
                  >
                    {{ u.is_active ? '禁用' : '启用' }}
                  </button>
                  <span v-else class="muted" style="font-size: 12px">当前账号</span>
                </td>
              </tr>
              <tr v-if="!filteredUsers.length">
                <td colspan="6"><div class="empty">无匹配用户</div></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 审计日志 -->
      <div v-else>
        <div class="toolbar">
          <select v-model="auditAction" class="select" style="width: 160px" @change="loadAuditLogs">
            <option value="">全部动作</option>
            <option v-for="(label, key) in actionLabels" :key="key" :value="key">{{ label }}</option>
          </select>
          <span class="muted" style="font-size: 12px">共 {{ auditTotal }} 条记录</span>
          <span class="spacer"></span>
          <button class="btn btn-ghost btn-sm" :disabled="loadingAudit" @click="loadAuditLogs">
            {{ loadingAudit ? '刷新中…' : '刷新' }}
          </button>
        </div>

        <div class="panel">
          <table class="table">
            <thead>
              <tr>
                <th style="width: 150px">时间</th>
                <th>操作人</th>
                <th>动作</th>
                <th>对象</th>
                <th>详情</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in auditLogs" :key="a.id">
                <td class="muted mono">{{ fmtTime(a.created_at) }}</td>
                <td class="mono">{{ a.username || '-' }}</td>
                <td>
                  <span class="tag tag-blue">{{ actionLabels[a.action] || a.action }}</span>
                </td>
                <td class="muted mono">
                  {{ a.target_type ? `${a.target_type}#${a.target_id ?? '-'}` : '-' }}
                </td>
                <td>{{ a.detail || '-' }}</td>
                <td class="muted mono">{{ a.ip || '-' }}</td>
              </tr>
              <tr v-if="!auditLogs.length">
                <td colspan="6"><div class="empty">{{ loadingAudit ? '加载中…' : '暂无审计记录' }}</div></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <AppModal v-if="rejecting" title="驳回资源" @close="rejecting = null">
      <div class="muted" style="margin-bottom: 12px; font-size: 13px">
        资源：{{ rejecting.name }}
      </div>
      <div class="field">
        <label class="field-label">驳回理由（选填）</label>
        <textarea v-model="rejectReason" class="textarea" placeholder="如：价格信息不完整" />
      </div>
      <template #footer>
        <button class="btn btn-ghost" @click="rejecting = null">取消</button>
        <button class="btn btn-danger" :disabled="busy === rejecting.id" @click="confirmReject">
          确认驳回
        </button>
      </template>
    </AppModal>
  </div>
</template>

<style scoped>
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
  display: flex;
  align-items: center;
  gap: 6px;
}
.tab.active { color: var(--accent-cyan); border-bottom-color: var(--accent-cyan); }
.badge {
  background: var(--accent-red);
  color: #fff;
  font-size: 10px;
  border-radius: 8px;
  padding: 1px 6px;
}
</style>
