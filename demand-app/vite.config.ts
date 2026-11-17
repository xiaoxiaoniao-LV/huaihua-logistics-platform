import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

export default defineConfig({
  plugins: [uni()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5174,
    host: '0.0.0.0',
    proxy: {
      // H5 开发环境走代理，避免跨域；小程序端由 VITE_API_BASE 指定后端地址
      '/api': { target: 'http://127.0.0.1:8002', changeOrigin: true },
    },
  },
})
