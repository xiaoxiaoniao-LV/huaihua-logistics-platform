import { clearSession, request, setSession } from './http'

export interface AppUser {
  id: number
  username: string
  role: string
  company_name: string | null
  contact: string | null
  credit_score: number
}

export async function loginApp(username: string, password: string) {
  const data = await request<{ access_token: string }>({
    url: '/api/v1/auth/login',
    method: 'POST',
    data: { username, password, client: 'app' },
  })
  setSession(data.access_token)
  return fetchMe()
}

export function registerApp(username: string, password: string, companyName?: string) {
  return request<AppUser>({
    url: '/api/v1/auth/register',
    method: 'POST',
    data: {
      username,
      password,
      role: 'demander',
      company_name: companyName || null,
    },
  })
}

export async function fetchMe() {
  const user = await request<AppUser>({ url: '/api/v1/users/me' })
  setSession(uni.getStorageSync('hlg_app_token') as string, user)
  return user
}

export function logout() {
  clearSession()
}
