import { createRouter, createWebHashHistory } from 'vue-router'

const TOKEN_KEY = 'hlg_token'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('@/views/Dashboard.vue') },
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
    {
      path: '/manage',
      component: () => import('@/views/ManageLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/manage/resources' },
        { path: 'market', name: 'market', component: () => import('@/views/MarketView.vue') },
        { path: 'resources', name: 'myResources', component: () => import('@/views/MyResourcesView.vue') },
        { path: 'orders', name: 'myOrders', component: () => import('@/views/MyOrdersView.vue') },
        { path: 'alerts', name: 'alerts', component: () => import('@/views/AlertsView.vue') },
        { path: 'devices', name: 'devices', component: () => import('@/views/DevicesView.vue') },
        { path: 'stats', name: 'stats', component: () => import('@/views/StatsView.vue') },
        { path: 'profile', name: 'profile', component: () => import('@/views/ProfileView.vue') },
        { path: 'admin', name: 'admin', component: () => import('@/views/AdminView.vue') },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  const loggedIn = !!localStorage.getItem(TOKEN_KEY)
  if (to.meta.requiresAuth && !loggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login' && loggedIn) {
    return { path: '/manage/resources' }
  }
})

export default router
