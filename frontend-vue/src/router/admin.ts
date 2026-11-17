/** 运营后台路由（admin.html）：供给工作台 + 管理员审核，按角色收敛可见范围。 */
import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const TOKEN_KEY = 'hlg_token'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
    {
      path: '/',
      component: () => import('@/views/ManageLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/workbench' },
        { path: 'workbench', name: 'workbench', component: () => import('@/views/WorkbenchView.vue') },
        { path: 'market', name: 'market', component: () => import('@/views/MarketView.vue') },
        { path: 'resources', name: 'myResources', component: () => import('@/views/MyResourcesView.vue') },
        { path: 'orders', name: 'myOrders', component: () => import('@/views/MyOrdersView.vue') },
        { path: 'alerts', name: 'alerts', component: () => import('@/views/AlertsView.vue') },
        { path: 'devices', name: 'devices', component: () => import('@/views/DevicesView.vue') },
        {
          path: 'twin',
          name: 'twinConfig',
          component: () => import('@/views/TwinConfigView.vue'),
          meta: { requiresRole: 'admin' },
        },
        {
          path: 'stats',
          name: 'stats',
          component: () => import('@/views/StatsView.vue'),
          meta: { requiresRole: 'admin' },
        },
        { path: 'profile', name: 'profile', component: () => import('@/views/ProfileView.vue') },
        {
          path: 'admin',
          name: 'admin',
          component: () => import('@/views/AdminView.vue'),
          meta: { requiresRole: 'admin' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/workbench' },
  ],
})

router.beforeEach(async (to) => {
  const loggedIn = !!localStorage.getItem(TOKEN_KEY)

  if (to.path === '/login') {
    return loggedIn ? { path: '/workbench' } : true
  }
  if (to.meta.requiresAuth && !loggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (!to.meta.requiresAuth) return true

  // 刷新页面后 store 为空，先补齐当前用户再做角色判断
  const auth = useAuthStore()
  if (!auth.user) {
    await auth.fetchMe()
    if (!auth.user) {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }
  const requiredRole = to.meta.requiresRole as string | undefined
  if (requiredRole && auth.user.role !== requiredRole) {
    return { path: '/workbench' }
  }
  return true
})

export default router
