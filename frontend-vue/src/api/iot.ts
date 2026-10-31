import { http } from './client'

export interface IoTDataPoint {
  device_code: string
  /** 设备绑定的资源 id，0 表示未绑定 */
  resource_id?: number
  temperature?: number | null
  humidity?: number | null
  longitude?: number | null
  latitude?: number | null
  recorded_at: string
}

export interface IoTAlert {
  id: number
  type: string
  level: 'critical' | 'warn' | 'info' | string
  message: string
  status: 'active' | 'resolved' | string
  device_id?: number
  device_code?: string | null
  /** 设备绑定的资源 id，0 表示未绑定 */
  resource_id?: number
  created_at: string
}

export function queryIoTData(params: { device_code?: string; limit?: number }) {
  return http.get<{ count: number; data: IoTDataPoint[] }>('/api/iot/data', { params })
}

export function listAlerts(params?: { status?: string; limit?: number }) {
  return http.get<{ count: number; alerts: IoTAlert[] }>('/api/iot/alerts', { params })
}

export function resolveAlert(id: number) {
  return http.post<{ id: number; status: string }>(`/api/iot/alerts/${id}/resolve`)
}

export interface AlertRule {
  id: number
  /** 0 表示全局默认规则 */
  resource_id: number
  temp_min: number
  temp_max: number
  humidity_max: number
  enabled: boolean
  updated_at?: string | null
  resource_name?: string | null
}

export function listAlertRules() {
  return http.get<AlertRule[]>('/api/iot/rules')
}

export function saveAlertRule(
  resourceId: number,
  payload: { temp_min?: number; temp_max?: number; humidity_max?: number; enabled?: boolean },
) {
  return http.put<AlertRule>(`/api/iot/rules/${resourceId}`, payload)
}

export function deleteAlertRule(resourceId: number) {
  return http.delete<void>(`/api/iot/rules/${resourceId}`)
}
