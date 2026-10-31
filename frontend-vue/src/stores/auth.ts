import { defineStore } from 'pinia'
import { fetchMe, login as apiLogin, register as apiRegister, type User } from '@/api/auth'

const TOKEN_KEY = 'hlg_token'
const REFRESH_TOKEN_KEY = 'hlg_refresh_token'

interface State {
  token: string
  refreshToken: string
  user: User | null
  loading: boolean
}

export const useAuthStore = defineStore('auth', {
  state: (): State => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY) || '',
    user: null,
    loading: false,
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
    isSupplier: (s) => s.user?.role === 'supplier',
    isDemander: (s) => s.user?.role === 'demander',
    isAdmin: (s) => s.user?.role === 'admin',
    displayName: (s) => s.user?.company_name || s.user?.username || '',
  },
  actions: {
    async login(username: string, password: string) {
      const { data } = await apiLogin(username, password)
      this.setTokens(data.access_token, data.refresh_token || '')
      await this.fetchMe()
    },
    setTokens(accessToken: string, refreshToken: string) {
      this.token = accessToken
      this.refreshToken = refreshToken
      localStorage.setItem(TOKEN_KEY, accessToken)
      if (refreshToken) localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
    },
    clearTokens() {
      this.token = ''
      this.refreshToken = ''
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(REFRESH_TOKEN_KEY)
    },
    async register(payload: {
      username: string
      password: string
      role: string
      company_name?: string
      contact?: string
    }) {
      await apiRegister(payload)
      await this.login(payload.username, payload.password)
    },
    async fetchMe() {
      if (!this.token) return
      this.loading = true
      try {
        const { data } = await fetchMe()
        this.user = data
      } catch {
        // 令牌失效：清理本地状态
        this.logout()
      } finally {
        this.loading = false
      }
    },
    logout() {
      this.clearTokens()
      this.user = null
    },
  },
})
