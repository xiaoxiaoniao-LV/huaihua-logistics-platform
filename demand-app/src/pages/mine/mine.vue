<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { fetchMe, loginApp, logout, registerApp, type AppUser } from '@/api/auth'
import { cachedUser, isLoggedIn } from '@/api/http'

const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const companyName = ref('')
const user = ref<AppUser | null>(cachedUser<AppUser>())
const loggedIn = ref(isLoggedIn())
const busy = ref(false)

const roleLabels: Record<string, string> = {
  demander: '需求方',
  supplier: '供给方',
  admin: '管理员',
}

async function refresh() {
  loggedIn.value = isLoggedIn()
  if (!loggedIn.value) {
    user.value = null
    return
  }
  user.value = cachedUser<AppUser>()
  try {
    user.value = await fetchMe()
  } catch (e) {
    loggedIn.value = isLoggedIn()
    user.value = cachedUser<AppUser>()
  }
}

function switchMode(m: 'login' | 'register') {
  mode.value = m
}

async function submit() {
  const u = username.value.trim()
  if (!u || !password.value) {
    uni.showToast({ title: '请输入账号和密码', icon: 'none' })
    return
  }
  if (u.length < 3) {
    uni.showToast({ title: '账号至少 3 位', icon: 'none' })
    return
  }
  if (mode.value === 'register' && password.value.length < 8) {
    uni.showToast({ title: '密码至少 8 位，需含字母和数字', icon: 'none' })
    return
  }
  busy.value = true
  try {
    if (mode.value === 'register') {
      await registerApp(u, password.value, companyName.value.trim() || undefined)
      uni.showToast({ title: '注册成功', icon: 'success' })
    }
    await loginApp(u, password.value)
    await refresh()
    uni.showToast({ title: '登录成功', icon: 'success' })
    password.value = ''
  } catch (e) {
    // request 已提示（如账号已存在、密码错误）
  } finally {
    busy.value = false
  }
}

function doLogout() {
  uni.showModal({
    title: '退出登录',
    content: '退出后仍可继续以游客身份浏览资源。',
    success: (res) => {
      if (!res.confirm) return
      logout()
      user.value = null
      loggedIn.value = false
      username.value = ''
      uni.showToast({ title: '已退出', icon: 'none' })
    },
  })
}

onShow(() => refresh())
</script>

<template>
  <view class="page">
    <view v-if="loggedIn && user" class="card profile">
      <view class="avatar">{{ (user.company_name || user.username).slice(0, 1) }}</view>
      <view class="p-name">{{ user.company_name || user.username }}</view>
      <view class="small muted">账号 {{ user.username }} · {{ roleLabels[user.role] || user.role }}</view>
      <view class="credit">
        <text class="credit-num">{{ user.credit_score }}</text>
        <text class="small muted"> 信用分</text>
      </view>
      <view class="divider" />
      <view class="kv">
        <text class="muted">联系方式</text>
        <text>{{ user.contact || '未填写' }}</text>
      </view>
      <view class="kv">
        <text class="muted">用户编号</text>
        <text class="mono">#{{ user.id }}</text>
      </view>
      <button class="btn btn-ghost logout" @tap="doLogout">退出登录</button>
    </view>

    <template v-else>
      <view class="card auth">
        <view class="tabs">
          <view class="tab" :class="{ 'tab-on': mode === 'login' }" @tap="switchMode('login')">登录</view>
          <view class="tab" :class="{ 'tab-on': mode === 'register' }" @tap="switchMode('register')">注册</view>
        </view>

        <view class="field">
          <text class="label">账号</text>
          <input v-model="username" class="input" placeholder="请输入用户名" />
        </view>
        <view class="field">
          <text class="label">密码</text>
          <input v-model="password" class="input" password placeholder="请输入密码" />
        </view>
        <view v-if="mode === 'register'" class="field">
          <text class="label">企业名称</text>
          <input v-model="companyName" class="input" placeholder="选填，便于供给方识别" />
        </view>

        <button class="btn submit" :disabled="busy" @tap="submit">
          {{ busy ? '处理中…' : mode === 'login' ? '登录' : '注册并登录' }}
        </button>
        <view class="small muted hint">
          {{ mode === 'login' ? '没有账号？切换到「注册」创建需求方账号' : '注册默认角色为需求方，可直接开始预约' }}
        </view>
      </view>

      <view class="card guest-tip">
        <view class="guest-title">游客模式</view>
        <view class="small muted">不登录也能浏览资源、查看智能撮合推荐；下单时需要账号。</view>
      </view>
    </template>

    <view class="small muted brand">怀化国际陆港冷链资源智能撮合平台 · 虚拟构建</view>
  </view>
</template>

<style scoped>
.profile { text-align: center; padding: 48rpx 36rpx 36rpx; }
.avatar {
  width: 108rpx;
  height: 108rpx;
  margin: 0 auto 18rpx;
  border-radius: 50%;
  background: linear-gradient(135deg, #12b3b8, #0a5b74);
  color: #fff;
  font-size: 44rpx;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.p-name { font-size: 34rpx; font-weight: 700; }
.credit { margin-top: 18rpx; }
.credit-num { font-size: 40rpx; font-weight: 700; color: #0a8f96; }
.divider { height: 1rpx; background: #eef2f7; margin: 26rpx 0 18rpx; }
.kv { display: flex; justify-content: space-between; font-size: 26rpx; padding: 10rpx 0; }
.logout { margin-top: 32rpx; }
.auth { padding: 36rpx 32rpx; }
.tabs { display: flex; background: #f2f6fb; border-radius: 999rpx; padding: 6rpx; margin-bottom: 30rpx; }
.tab {
  flex: 1;
  text-align: center;
  padding: 16rpx 0;
  font-size: 28rpx;
  color: #4a6076;
  border-radius: 999rpx;
}
.tab-on { background: #fff; color: #0a7fa3; font-weight: 700; box-shadow: 0 4rpx 12rpx rgba(15, 58, 96, 0.08); }
.field { margin-bottom: 22rpx; }
.label { font-size: 24rpx; color: #7d8fa3; }
.input {
  margin-top: 10rpx;
  background: #f7fafd;
  border: 1rpx solid #e2eaf2;
  border-radius: 14rpx;
  padding: 20rpx 24rpx;
  font-size: 28rpx;
}
.submit { margin-top: 12rpx; }
.hint { text-align: center; margin-top: 20rpx; }
.guest-tip { padding: 30rpx; }
.guest-title { font-size: 28rpx; font-weight: 700; margin-bottom: 8rpx; }
.brand { text-align: center; margin-top: 50rpx; }
</style>
