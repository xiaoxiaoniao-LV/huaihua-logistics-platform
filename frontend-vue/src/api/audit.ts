import { http } from './client'

export interface AuditLogItem {
  id: number
  user_id?: number | null
  username?: string | null
  action: string
  target_type?: string | null
  target_id?: number | null
  detail?: string | null
  ip?: string | null
  created_at: string
}

export function listAuditLogs(params?: {
  action?: string
  username?: string
  page?: number
  page_size?: number
}) {
  return http.get<AuditLogItem[]>('/api/audit-logs', { params })
}
