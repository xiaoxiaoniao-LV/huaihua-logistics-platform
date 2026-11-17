/** 指挥大屏路由：单页只读，任何未知路径都回落总览。 */
import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'screen', component: () => import('@/views/Dashboard.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
