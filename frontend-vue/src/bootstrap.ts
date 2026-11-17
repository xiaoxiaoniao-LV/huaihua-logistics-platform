/** 多页应用共用启动逻辑：screen.html / admin.html 各自挂载独立路由。 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import type { Router } from 'vue-router'
import App from './App.vue'
import './style.css'
// 主题令牌注入根元素（CSS 变量唯一来源）+ ECharts 品牌主题注册
import { applyTheme } from '@/config/theme'
import '@/config/echartsTheme'

export function bootstrap(router: Router) {
  applyTheme()
  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.mount('#app')
}
