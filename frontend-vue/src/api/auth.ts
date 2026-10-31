import { http } from './client'

export interface User {
  id: number
  username: string
  role: 'supplier' | 'demander' | 'admin' | string
  company_name?: string | null
  contact?: string | null
  credit_score: number
  is_active?: boolean
  created_at: string
}

export interface Token {
  access_token: string
  refresh_token?: string
  token_type: string
}

export function login(username: string, password: string) {
  return http.post<Token>('/api/auth/login', { username, password })
}

export function refresh(refreshToken: string) {
  return http.post<Token>('/api/auth/refresh', { refresh_token: refreshToken })
}

export function changePassword(oldPassword: string, newPassword: string) {
  return http.post<User>('/api/auth/change-password', {
    old_password: oldPassword,
    new_password: newPassword,
  })
}

export function register(payload: {
  username: string
  password: string
  role: string
  company_name?: string
  contact?: string
}) {
  return http.post<User>('/api/auth/register', payload)
}

export function fetchMe() {
  return http.get<User>('/api/users/me')
}

export function updateMe(payload: { company_name?: string | null; contact?: string | null }) {
  return http.put<User>('/api/users/me', payload)
}
