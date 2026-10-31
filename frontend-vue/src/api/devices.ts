import { http } from './client'

export interface Device {
  id: number
  device_code: string
  device_type?: string | null
  resource_id: number
  status: 'online' | 'offline' | string
  resource_name?: string | null
  last_seen?: string | null
  last_temperature?: number | null
  last_humidity?: number | null
}

export function listDevices(params?: { resource_id?: number; status?: string }) {
  return http.get<Device[]>('/api/devices', { params })
}

export function createDevice(payload: { device_code: string; device_type?: string; resource_id?: number }) {
  return http.post<Device>('/api/devices', payload)
}

export function updateDevice(
  id: number,
  payload: { resource_id?: number; device_type?: string; status?: string },
) {
  return http.put<Device>(`/api/devices/${id}`, payload)
}

export function deleteDevice(id: number) {
  return http.delete<void>(`/api/devices/${id}`)
}

export function autoBindDevices() {
  return http.post<{ bound: number; detail: string }>('/api/devices/auto-bind')
}

export interface TelemetryPoint {
  temperature?: number | null
  humidity?: number | null
  longitude?: number | null
  latitude?: number | null
  recorded_at: string
}

export function getDeviceTelemetry(id: number, limit = 100) {
  return http.get<{ device_code: string; resource_id: number; count: number; data: TelemetryPoint[] }>(
    `/api/devices/${id}/telemetry`,
    { params: { limit } },
  )
}
