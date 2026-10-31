<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { apiError } from '@/utils/error'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const mode = ref<'login' | 'register'>('login')
const submitting = ref(false)
const error = ref('')

const form = reactive({
  username: '',
  password: '',
  confirm: '',
  role: 'demander',
  company_name: '',
  contact: '',
})

const title = computed(() => (mode.value === 'login' ? '登录' : '注册'))

function switchMode(next: 'login' | 'register') {
  mode.value = next
  error.value = ''
}

async function submit() {
  error.value = ''
  if (!form.username.trim() || !form.password) {
    error.value = '请填写用户名和密码'
    return
  }
  if (mode.value === 'register') {
    if (form.password.length < 8) {
      error.value = '密码至少 8 位'
      return
    }
    if (!/[A-Za-z]/.test(form.password) || !/\d/.test(form.password)) {
      error.value = '密码必须同时包含字母和数字'
      return
    }
    if (form.password !== form.confirm) {
      error.value = '两次输入的密码不一致'
      return
    }
  }

  submitting.value = true
  try {
    if (mode.value === 'login') {
      await auth.login(form.username.trim(), form.password)
    } else {
      await auth.register({
        username: form.username.trim(),
        password: form.password,
        role: form.role,
        company_name: form.company_name || undefined,
        contact: form.contact || undefined,
      })
    }
    const redirect = (route.query.redirect as string) || '/manage/resources'
    router.replace(redirect)
  } catch (e) {
    error.value = apiError(e, mode.value === 'login' ? '登录失败' : '注册失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <div class="brand-title">怀化国际陆港</div>
        <div class="brand-sub">物流资源共享与智能撮合平台</div>
      </div>

      <div class="tabs">
        <button class="tab" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
        <button class="tab" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
      </div>

      <form @submit.prevent="submit">
        <div class="field">
          <label class="field-label">用户名</label>
          <input v-model="form.username" class="input" autocomplete="username" placeholder="请输入用户名" />
        </div>

        <div class="field">
          <label class="field-label">密码</label>
          <input
            v-model="form.password"
            class="input"
            type="password"
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
            placeholder="请输入密码"
          />
        </div>

        <template v-if="mode === 'register'">
          <div class="field">
            <label class="field-label">确认密码</label>
            <input v-model="form.confirm" class="input" type="password" autocomplete="new-password" placeholder="再次输入密码" />
            <div class="field-hint">至少 8 位，且同时包含字母和数字</div>
          </div>

          <div class="field">
            <label class="field-label">账号类型</label>
            <select v-model="form.role" class="select">
              <option value="demander">需求方（租用资源）</option>
              <option value="supplier">供给方（发布资源）</option>
            </select>
          </div>

          <div class="field-row">
            <div class="field">
              <label class="field-label">企业名称（选填）</label>
              <input v-model="form.company_name" class="input" placeholder="如：怀化冷链物流有限公司" />
            </div>
            <div class="field">
              <label class="field-label">联系方式（选填）</label>
              <input v-model="form.contact" class="input" placeholder="手机号" />
            </div>
          </div>
        </template>

        <div class="error-text">{{ error }}</div>

        <button class="btn submit" type="submit" :disabled="submitting">
          {{ submitting ? '处理中…' : title }}
        </button>
      </form>

      <div class="back">
        <RouterLink to="/" class="link">← 返回数字孪生大屏</RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.login-card {
  width: 400px;
  max-width: 100%;
  background: var(--bg-card);
  border: 1px solid var(--border-glow);
  border-radius: 12px;
  padding: 28px 28px 22px;
  backdrop-filter: blur(12px);
  box-shadow: 0 16px 64px rgba(0, 0, 0, 0.5);
  position: relative;
  overflow: hidden;
}
.login-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--accent-cyan), transparent);
}
.brand { text-align: center; margin-bottom: 22px; }
.brand-title {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 4px;
  background: linear-gradient(90deg, var(--accent-cyan), var(--accent));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.brand-sub { font-size: 11px; color: var(--text-muted); letter-spacing: 2px; margin-top: 6px; }

.tabs {
  display: flex;
  border-bottom: 1px solid var(--border-glow);
  margin-bottom: 18px;
}
.tab {
  flex: 1;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 14px;
  padding: 9px 0;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}
.tab.active { color: var(--accent-cyan); border-bottom-color: var(--accent-cyan); }

.submit { width: 100%; padding: 10px; font-size: 14px; margin-top: 4px; }
.back { text-align: center; margin-top: 16px; }
</style>
