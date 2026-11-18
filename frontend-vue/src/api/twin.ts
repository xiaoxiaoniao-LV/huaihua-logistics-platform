/** 数字孪生读模型接口（大屏只读，允许匿名）。 */
import { http } from './client'

export interface TwinBinding {
  id: number
  binding_type: string
  device_code: string
  device_name?: string
  device_status: string
  point_key: string
  name: string
  unit: string | null
  data_type: string
  value: number | string | boolean | null
  quality: string
  ts: string | null
}

export interface TwinNode {
  id: number
  node_key: string
  name: string
  node_type: string
  parent_id: number | null
  space_id: number | null
  model_ref?: string | null
  transform?: Record<string, any> | null
  status: string
  bindings: TwinBinding[]
  children: TwinNode[]
}

export interface TwinDeviceRow {
  device_code: string
  name: string
  device_type: string
  status: string
  quality: string
  resource_id: number
  space_id: number | null
  last_seen_at: string | null
  age_ms: number | null
  point_count: number
}

export interface TwinEventRow {
  id: number
  device_code: string | null
  event_type: string
  severity: string
  message: string | null
  ts: string | null
  resolved_at: string | null
}

export interface TwinSnapshot {
  generated_at: string
  count: number
  summary: Record<string, number>
  tree: TwinNode[]
  flat: Omit<TwinNode, 'children'>[]
  devices: {
    total: number
    by_status: Record<string, number>
    items: TwinDeviceRow[]
  }
  alerts: {
    count: number
    items: {
      id: number
      type: string
      level: string
      message: string
      device_code: string | null
      created_at: string | null
    }[]
  }
  events: { count: number; items: TwinEventRow[] }
}

export interface DevicePointState {
  point_key: string
  name: string
  unit: string | null
  data_type: string
  precision: number
  min_value: number | null
  max_value: number | null
  writable: boolean
  sort: number
  value: number | string | boolean | null
  quality: string
  ts: string | null
  age_ms: number | null
}

export interface DeviceState {
  device_code: string
  name: string
  resource_id: number
  space_id: number | null
  status: string
  quality: string
  last_seen_at: string | null
  age_ms: number | null
  points: DevicePointState[]
}

export interface SeriesPoint {
  ts: string
  value: number | boolean | string | null
  value_num: number | null
  value_text: string | null
  quality: string
}

export function fetchTwinSnapshot() {
  return http.get<TwinSnapshot>('/api/v1/twin/snapshot')
}

// ---------- 孪生配置（管理端写接口，需 admin 令牌） ----------

export interface TwinConfigNode {
  id: number
  node_key: string
  name: string
  node_type: string
  parent_id: number | null
  space_id: number | null
  model_ref?: string | null
  transform?: Record<string, unknown> | null
  sort?: number
  status: string
  bindings: TwinBinding[]
  children: TwinConfigNode[]
}

export interface TwinTree {
  generated_at?: string
  count: number
  summary: Record<string, number>
  tree: TwinConfigNode[]
}

export interface SpaceNode {
  id: number
  code: string
  name: string
  kind: string
  parent_id: number | null
  capacity?: number | null
  geo?: Record<string, unknown> | null
  sort: number
  enabled: boolean
  children: SpaceNode[]
}

export interface TwinNodePayload {
  node_key: string
  name: string
  node_type: string
  parent_id?: number | null
  space_id?: number | null
  model_ref?: string | null
  transform?: Record<string, unknown> | null
  sort?: number
}

export interface DevicePointOption {
  id: number
  point_key: string
  name: string
  unit: string | null
  data_type: string
  min_value: number | null
  max_value: number | null
  writable: boolean
  sort: number
}

export function fetchTwinTree() {
  return http.get<TwinTree>('/api/v1/twin/tree')
}

export function fetchSpaceTree() {
  return http.get<{ count: number; tree: SpaceNode[] }>('/api/v1/twin/spaces')
}

export function saveTwinNode(payload: TwinNodePayload) {
  return http.post<{ created: boolean; id: number; node_key: string }>('/api/v1/twin/nodes', payload)
}

export function bindTwinPoint(payload: {
  node_key: string
  device_code: string
  point_key: string
  binding_type: string
}) {
  return http.post<{ created: boolean; id: number }>('/api/v1/twin/bindings', payload)
}

export function deleteTwinBinding(bindingId: number) {
  return http.delete<void>(`/api/v1/twin/bindings/${bindingId}`)
}

export function fetchDevicePoints(deviceCode: string) {
  return http.get<{ device_code: string; count: number; points: DevicePointOption[] }>(
    `/api/v1/iot/devices/${deviceCode}/points`,
  )
}

export function fetchDeviceState(deviceCode: string) {
  return http.get<DeviceState>(`/api/v1/iot/devices/${deviceCode}/state`)
}

export function fetchDeviceSeries(deviceCode: string, pointKey: string, limit = 60) {
  return http.get<{
    device_code: string
    point_key: string
    unit: string | null
    count: number
    data: SeriesPoint[]
  }>('/api/v1/iot/devices/' + deviceCode + '/series', {
    params: { point_key: pointKey, limit },
  })
}

export function fetchDeviceEvents(deviceCode: string, limit = 20) {
  return http.get<{ device_code: string; count: number; events: TwinEventRow[] }>(
    `/api/v1/iot/devices/${deviceCode}/events`,
    { params: { limit } },
  )
}
