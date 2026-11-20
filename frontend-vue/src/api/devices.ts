import { http } from './client'

export interface Device {
  id: number
  device_code: string
  device_type?: string | null
  resource_id: number
  status: 'online' | 'offline' | string
  firmware_version?: string
  resource_name?: string | null
  last_seen?: string | null
  last_temperature?: number | null
  last_humidity?: number | null
}

export function listDevices(params?: { resource_id?: number; status?: string }) {
  return http.get<Device[]>('/api/v1/devices', { params })
}

export function createDevice(payload: { device_code: string; device_type?: string; resource_id?: number }) {
  return http.post<Device>('/api/v1/devices', payload)
}

export function updateDevice(
  id: number,
  payload: { resource_id?: number; device_type?: string; status?: string },
) {
  return http.put<Device>(`/api/v1/devices/${id}`, payload)
}

export function deleteDevice(id: number) {
  return http.delete<void>(`/api/v1/devices/${id}`)
}

export function autoBindDevices() {
  return http.post<{ bound: number; detail: string }>('/api/v1/devices/auto-bind')
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
    `/api/v1/devices/${id}/telemetry`,
    { params: { limit } },
  )
}

export interface ImportErrorItem {
  row: number
  device_code?: string | null
  reason: string
}

export interface ImportResult {
  created: number
  skipped: number
  failed: number
  errors: ImportErrorItem[]
}

/** 批量导入设备（CSV 文件）。 */
export function importDevices(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return http.post<ImportResult>('/api/v1/devices/import', fd)
}

export interface OtaTask {
  id: number
  device_id: number
  device_code?: string | null
  from_version?: string | null
  target_version: string
  status: 'pending' | 'running' | 'success' | 'failed' | string
  message?: string | null
  batch_id?: string | null
  stage?: string | null
  created_at?: string | null
  finished_at?: string | null
}

export interface OtaBatch {
  batch_id: string
  target_version: string
  stage: 'canary' | 'full' | 'rollback' | string
  status: 'running' | 'done' | 'failed' | 'rolled_back' | string
  rollout_percent: number
  rollback_of?: string | null
  total: number
  pending: number
  running: number
  success: number
  failed: number
}

export function listOtaTasks(limit = 20) {
  return http.get<OtaTask[]>('/api/v1/devices/ota', { params: { limit } })
}

/** 创建批量升级任务；device_ids 为空表示全部设备，rollout_percent<100 走灰度。 */
export function createOtaJob(payload: {
  target_version: string
  device_ids?: number[]
  space_id?: number
  rollout_percent?: number
}) {
  return http.post<OtaTask[]>('/api/v1/devices/ota', payload)
}

export function getOtaBatch(batchId: string) {
  return http.get<OtaBatch>(`/api/v1/devices/ota/batch/${batchId}`)
}

/** 灰度批次续发为全量。 */
export function promoteOtaBatch(batchId: string) {
  return http.post<OtaBatch>(`/api/v1/devices/ota/batch/${batchId}/promote`)
}

/** 回滚批次；不传版本时回到该批次升级前的版本。 */
export function rollbackOtaBatch(batchId: string, target_version?: string) {
  return http.post<OtaBatch>(`/api/v1/devices/ota/batch/${batchId}/rollback`, {
    target_version,
  })
}
