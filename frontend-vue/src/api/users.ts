import { http } from './client'

export interface AdminUser {
  id: number
  username: string
  role: 'supplier' | 'demander' | 'admin' | string
  company_name?: string | null
  contact?: string | null
  credit_score: number
  is_active: boolean
  created_at: string
}

export function listUsers(params?: { keyword?: string; role?: string; is_active?: boolean }) {
  return http.get<AdminUser[]>('/api/users', { params })
}

export function adminUpdateUser(
  id: number,
  payload: { role?: string; is_active?: boolean; company_name?: string; contact?: string },
) {
  return http.put<AdminUser>(`/api/users/${id}`, payload)
}
