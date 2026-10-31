import axios from 'axios'

const BASE = (import.meta.env.VITE_API_BASE as string) || ''

export const http = axios.create({
  baseURL: BASE,
  timeout: 10000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('hlg_token')
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 401 时的无感续期：用 refresh token 换取新 access token 后重试原请求。
// 用模块级 Promise 合并并发刷新，避免同一时刻多个请求重复调 refresh。
let refreshPromise: Promise<string> | null = null

function tryRefresh(): Promise<string> {
  const refreshToken = localStorage.getItem('hlg_refresh_token')
  if (!refreshToken) return Promise.reject(new Error('no refresh token'))
  if (!refreshPromise) {
    refreshPromise = axios
      .post(
        `${BASE}/api/auth/refresh`,
        { refresh_token: refreshToken },
        { timeout: 10000 },
      )
      .then((r) => {
        const access = r.data.access_token as string
        localStorage.setItem('hlg_token', access)
        if (r.data.refresh_token) {
          localStorage.setItem('hlg_refresh_token', r.data.refresh_token)
        }
        return access
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

http.interceptors.response.use(
  (r) => r,
  async (err) => {
    const status: number | undefined = err?.response?.status
    const config = err?.config
    const cfg = config as (typeof config & { _retry?: boolean }) | undefined

    if (status === 401 && cfg && !cfg._retry) {
      cfg._retry = true
      try {
        const token = await tryRefresh()
        cfg.headers.Authorization = `Bearer ${token}`
        return http(cfg)
      } catch {
        localStorage.removeItem('hlg_token')
        localStorage.removeItem('hlg_refresh_token')
      }
    } else if (status === 401) {
      // 刷新失败或已是重试：清除本地令牌
      localStorage.removeItem('hlg_token')
      localStorage.removeItem('hlg_refresh_token')
    }

    console.warn('[API]', config?.url, err?.response?.data || err.message)
    return Promise.reject(err)
  },
)
