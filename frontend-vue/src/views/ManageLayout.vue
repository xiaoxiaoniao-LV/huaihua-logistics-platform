<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const roleLabel: Record<string, string> = {
  supplier: '供给方',
  demander: '需求方',
  admin: '管理员',
}

onMounted(() => {
  if (!auth.user) auth.fetchMe()
})

function logout() {
  auth.logout()
  router.replace('/login')
}
</script>

<template>
  <div class="manage">
    <header class="topbar">
      <div class="left">
        <span class="logo">怀化国际陆港</span>
        <span class="divider">|</span>
        <span class="caption">运营管理</span>
      </div>

      <nav class="nav">
        <RouterLink to="/manage/market" class="nav-item">资源市场</RouterLink>
        <RouterLink to="/manage/resources" class="nav-item">我的资源</RouterLink>
        <RouterLink to="/manage/orders" class="nav-item">我的订单</RouterLink>
        <RouterLink to="/manage/alerts" class="nav-item">告警处理</RouterLink>
        <RouterLink to="/manage/devices" class="nav-item">设备管理</RouterLink>
        <RouterLink v-if="auth.isAdmin" to="/manage/stats" class="nav-item">运营统计</RouterLink>
        <RouterLink to="/manage/profile" class="nav-item">个人中心</RouterLink>
        <RouterLink v-if="auth.isAdmin" to="/manage/admin" class="nav-item">审核与用户</RouterLink>
      </nav>

      <div class="right">
        <RouterLink to="/" class="ghost-link">数字孪生大屏</RouterLink>
        <div v-if="auth.user" class="user">
          <span class="name">{{ auth.displayName }}</span>
          <span class="tag tag-blue">{{ roleLabel[auth.user.role] || auth.user.role }}</span>
          <span class="credit">信用 {{ auth.user.credit_score }}</span>
        </div>
        <button class="btn btn-ghost btn-sm" @click="logout">退出</button>
      </div>
    </header>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.manage {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-rows: 56px 1fr;
  background: var(--bg-primary);
}
.topbar {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 20px;
  border-bottom: 1px solid var(--border-glow);
  background: linear-gradient(180deg, rgba(10, 26, 54, 0.95), rgba(5, 13, 31, 0.95));
}
.left { display: flex; align-items: center; gap: 10px; }
.logo {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 2px;
  background: linear-gradient(90deg, var(--accent-cyan), var(--accent));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.divider { color: var(--text-muted); }
.caption { font-size: 12px; color: var(--text-muted); letter-spacing: 2px; }

.nav { display: flex; gap: 4px; }
.nav-item {
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 4px;
  transition: all 0.2s;
}
.nav-item:hover { color: var(--accent-cyan); background: rgba(0, 229, 255, 0.06); }
.nav-item.router-link-active {
  color: var(--accent-cyan);
  background: rgba(0, 229, 255, 0.12);
}

.right { margin-left: auto; display: flex; align-items: center; gap: 14px; }
.ghost-link {
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 13px;
}
.ghost-link:hover { color: var(--accent-cyan); }
.user { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.name { color: var(--text-primary); }
.credit { color: var(--accent-orange); font-family: 'Consolas', monospace; font-size: 12px; }

.content { overflow: hidden; }

/* ===== 移动端：顶部栏换行、导航横向滚动 ===== */
@media (max-width: 768px) {
  .manage { grid-template-rows: auto 1fr; }
  .topbar {
    flex-wrap: wrap;
    gap: 6px 10px;
    padding: 8px 12px;
  }
  .left { gap: 8px; }
  .nav {
    order: 3;
    width: 100%;
    overflow-x: auto;
    padding-bottom: 4px;
  }
  .nav-item { white-space: nowrap; padding: 5px 10px; }
  .right { margin-left: 0; gap: 10px; width: 100%; justify-content: flex-end; }
  .user .name { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .content { overflow: visible; }
}
</style>
