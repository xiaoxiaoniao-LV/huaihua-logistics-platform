/** 需求端请求封装：游客可读，写操作自动带 App 端令牌。 */
const BASE = import.meta.env.VITE_API_BASE || ''

export const TOKEN_KEY = 'hlg_app_token'
export const USER_KEY = 'hlg_app_user'

export function getToken(): string {
  return (uni.getStorageSync(TOKEN_KEY) as string) || ''
}

export function isLoggedIn(): boolean {
  return !!getToken()
}

export function setSession(token: string, user?: unknown) {
  uni.setStorageSync(TOKEN_KEY, token)
  if (user) uni.setStorageSync(USER_KEY, user)
}

export function cachedUser<T>(): T | null {
  return (uni.getStorageSync(USER_KEY) as T) || null
}

export function clearSession() {
  uni.removeStorageSync(TOKEN_KEY)
  uni.removeStorageSync(USER_KEY)
}

interface RequestOptions {
  url: string
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  data?: Record<string, unknown>
  header?: Record<string, string>
  /** 静默模式：失败时不弹 toast（用于可选信息的后台补全） */
  silent?: boolean
}

function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item as { msg?: string })?.msg || '')
      .filter(Boolean)
      .join('；') || `请求失败（${status}）`
  }
  return `请求失败（${status}）`
}

export function request<T>(options: RequestOptions): Promise<T> {
  return new Promise((resolve, reject) => {
    const token = getToken()
    uni.request({
      url: `${BASE}${options.url}`,
      method: options.method || 'GET',
      data: options.data,
      header: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.header || {}),
      },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data as T)
          return
        }
        if (res.statusCode === 401) clearSession()
        const message = errorMessage(res.statusCode, res.data)
        if (!options.silent) {
          uni.showToast({ title: message, icon: 'none', duration: 2200 })
        }
        reject(new Error(message))
      },
      fail: (err) => {
        if (!options.silent) {
          uni.showToast({ title: '网络异常，请稍后重试', icon: 'none' })
        }
        reject(err)
      },
    })
  })
}

export function query(params: Record<string, string | number | undefined | null>): string {
  const pairs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  return pairs.length ? `?${pairs.join('&')}` : ''
}

export function idempotencyKey(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}
