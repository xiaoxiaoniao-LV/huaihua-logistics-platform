<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { changePassword, updateMe } from '@/api/auth'
import { getUserRating, type UserRatingSummary } from '@/api/reviews'
import { useAuthStore } from '@/stores/auth'
import { apiError } from '@/utils/error'

const auth = useAuthStore()

const roleLabels: Record<string, string> = {
  supplier: '供给方', demander: '需求方', admin: '管理员',
}

const form = reactive({ company_name: '', contact: '' })
const saving = ref(false)
const saved = ref(false)
const error = ref('')

const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })
const savingPwd = ref(false)
const pwdSaved = ref(false)
const pwdError = ref('')

const summary = ref<UserRatingSummary | null>(null)
const loadingSummary = ref(false)

const stars = computed(() => {
  const avg = summary.value?.average || 0
  const full = Math.round(avg)
  return '★'.repeat(full) + '☆'.repeat(Math.max(0, 5 - full))
})

async function loadSummary() {
  if (!auth.user) return
  loadingSummary.value = true
  try {
    const { data } = await getUserRating(auth.user.id)
    summary.value = data
  } catch {
    summary.value = null
  } finally {
    loadingSummary.value = false
  }
}

async function save() {
  error.value = ''
  saved.value = false
  saving.value = true
  try {
    const { data } = await updateMe({
      company_name: form.company_name.trim() || null,
      contact: form.contact.trim() || null,
    })
    auth.user = data
    saved.value = true
    window.setTimeout(() => (saved.value = false), 2000)
  } catch (e) {
    error.value = apiError(e, '保存失败')
  } finally {
    saving.value = false
  }
}

async function changePwd() {
  pwdError.value = ''
  pwdSaved.value = false
  if (!pwdForm.old_password || !pwdForm.new_password) {
    pwdError.value = '请填写旧密码和新密码'
    return
  }
  if (pwdForm.new_password.length < 8) {
    pwdError.value = '新密码至少 8 位'
    return
  }
  if (pwdForm.new_password !== pwdForm.confirm) {
    pwdError.value = '两次输入的新密码不一致'
    return
  }
  savingPwd.value = true
  try {
    await changePassword(pwdForm.old_password, pwdForm.new_password)
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm = ''
    pwdSaved.value = true
    window.setTimeout(() => (pwdSaved.value = false), 2000)
  } catch (e) {
    pwdError.value = apiError(e, '修改失败')
  } finally {
    savingPwd.value = false
  }
}

onMounted(async () => {
  if (!auth.user) await auth.fetchMe()
  form.company_name = auth.user?.company_name || ''
  form.contact = auth.user?.contact || ''
  await loadSummary()
})
</script>

<template>
  <div class="page-scroll">
    <div class="grid">
      <div class="panel">
        <div class="panel-title">基本信息</div>
        <div class="panel-body">
          <div class="field-row">
            <div class="field">
              <label class="field-label">用户名</label>
              <input class="input" :value="auth.user?.username || ''" disabled />
            </div>
            <div class="field">
              <label class="field-label">账号类型</label>
              <input class="input" :value="roleLabels[auth.user?.role || ''] || auth.user?.role || ''" disabled />
            </div>
          </div>

          <div class="field">
            <label class="field-label">企业名称</label>
            <input v-model="form.company_name" class="input" placeholder="如：怀化冷链物流有限公司" />
          </div>

          <div class="field">
            <label class="field-label">联系方式</label>
            <input v-model="form.contact" class="input" placeholder="手机号" />
          </div>

          <div class="field">
            <label class="field-label">注册时间</label>
            <input class="input mono" :value="(auth.user?.created_at || '').replace('T', ' ').slice(0, 19)" disabled />
          </div>

          <div class="error-text">{{ error }}</div>

          <div class="actions">
            <button class="btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存资料' }}</button>
            <span v-if="saved" class="ok">已保存</span>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">信用与评价</div>
        <div class="panel-body">
          <div class="credit-block">
            <div class="credit-value">{{ summary?.credit_score ?? auth.user?.credit_score ?? 100 }}</div>
            <div class="credit-label">信用分</div>
          </div>
          <div class="divider-line"></div>
          <div class="kv">
            <span class="muted">收到评价</span>
            <span class="mono">{{ summary?.count ?? 0 }} 条</span>
          </div>
          <div class="kv">
            <span class="muted">平均评分</span>
            <span class="mono">
              {{ summary && summary.count ? summary.average.toFixed(2) : '-' }}
              <span class="stars">{{ summary && summary.count ? stars : '' }}</span>
            </span>
          </div>
          <div class="hint">信用分由收到的评价自动重算：5 星 = 100 分，1 星 = 60 分。</div>
        </div>
      </div>
    </div>

    <div class="panel" style="margin-top: 16px">
      <div class="panel-title">账号安全</div>
      <div class="panel-body">
        <div class="field-row">
          <div class="field">
            <label class="field-label">旧密码</label>
            <input v-model="pwdForm.old_password" class="input" type="password" autocomplete="current-password" />
          </div>
          <div class="field">
            <label class="field-label">新密码</label>
            <input v-model="pwdForm.new_password" class="input" type="password" autocomplete="new-password" />
          </div>
          <div class="field">
            <label class="field-label">确认新密码</label>
            <input v-model="pwdForm.confirm" class="input" type="password" autocomplete="new-password" />
          </div>
        </div>
        <div class="field-hint">至少 8 位，且同时包含字母和数字；修改后下次登录请使用新密码。</div>
        <div class="error-text">{{ pwdError }}</div>
        <div class="actions">
          <button class="btn" :disabled="savingPwd" @click="changePwd">
            {{ savingPwd ? '提交中…' : '修改密码' }}
          </button>
          <span v-if="pwdSaved" class="ok">修改成功</span>
        </div>
      </div>
    </div>

    <div class="panel" style="margin-top: 16px">
      <div class="panel-title">收到的评价</div>
      <div class="panel-body">
        <div v-if="loadingSummary" class="empty">加载中…</div>
        <div v-else-if="!summary || !summary.reviews.length" class="empty">暂无评价</div>
        <div v-else class="review-list">
          <div v-for="r in summary?.reviews || []" :key="r.id" class="review-item">
            <div class="review-head">
              <span class="reviewer">{{ r.from_username || `用户 #${r.from_user_id}` }}</span>
              <span class="review-stars">{{ '★'.repeat(r.rating) }}{{ '☆'.repeat(Math.max(0, 5 - r.rating)) }}</span>
              <span class="review-order muted mono">订单 #{{ r.order_id }}</span>
              <span class="spacer"></span>
              <span class="review-time muted">{{ r.created_at.replace('T', ' ').slice(0, 16) }}</span>
            </div>
            <div class="review-content">{{ r.content || '（未填写评价内容）' }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  gap: 16px;
}
@media (max-width: 900px) {
  .grid { grid-template-columns: 1fr; }
}
.mono { font-family: 'Consolas', 'Monaco', monospace; }
.actions { display: flex; align-items: center; gap: 12px; margin-top: 8px; }
.ok { color: var(--accent-green); font-size: 12px; }

.credit-block { text-align: center; padding: 8px 0 4px; }
.credit-value {
  font-size: 44px;
  font-weight: 700;
  line-height: 1;
  color: var(--accent-orange);
  font-family: 'Consolas', 'Monaco', monospace;
}
.credit-label { font-size: 12px; color: var(--text-muted); margin-top: 6px; letter-spacing: 2px; }
.divider-line { height: 1px; background: var(--border-glow); margin: 14px 0; }
.kv { display: flex; justify-content: space-between; font-size: 13px; padding: 6px 0; }
.stars { color: var(--accent-orange); margin-left: 6px; letter-spacing: 1px; }
.hint { font-size: 11px; color: var(--text-muted); margin-top: 10px; line-height: 1.6; }

.review-list { display: flex; flex-direction: column; gap: 10px; }
.review-item {
  border-left: 2px solid var(--border-glow);
  padding: 6px 0 6px 12px;
}
.review-head { display: flex; align-items: center; gap: 10px; font-size: 12px; }
.reviewer { color: var(--text-primary); font-weight: 600; }
.review-stars { color: var(--accent-orange); letter-spacing: 1px; }
.review-order { font-size: 11px; }
.review-time { font-size: 11px; }
.spacer { flex: 1; }
.review-content { font-size: 13px; color: var(--text-secondary); margin-top: 4px; line-height: 1.6; }
</style>
