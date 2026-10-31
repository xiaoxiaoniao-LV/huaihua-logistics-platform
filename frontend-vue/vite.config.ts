import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // three / echarts 体积大且相互独立，单独成 chunk；其余依赖交给默认分包
        // 注意：不要把 axios / vue 等放进同一手动 chunk，跨 chunk 循环引用会导致运行时取到 undefined
        manualChunks(id: string) {
          if (id.includes('node_modules/three')) return 'three'
          if (id.includes('node_modules/echarts') || id.includes('node_modules/zrender')) return 'echarts'
        },
      },
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      // 后端 FastAPI 8002
      '/api': { target: 'http://127.0.0.1:8002', changeOrigin: true },
      '/ws': { target: 'http://127.0.0.1:8002', ws: true, changeOrigin: true },
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.test.ts'],
  },
})
