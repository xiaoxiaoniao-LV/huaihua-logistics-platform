import { defineStore } from 'pinia'
import {
  queryIoTData, listAlerts, resolveAlert as apiResolveAlert,
  type IoTDataPoint, type IoTAlert,
} from '@/api/iot'

interface State {
  // 设备代码 -> 最新一条数据
  latest: Record<string, IoTDataPoint>
  // 资源 id -> 该资源下设备的最新一条数据（弹窗/3D 展示用）
  latestByResource: Record<number, IoTDataPoint>
  // 实时数据滚动窗口（最多 200 条）
  timeline: IoTDataPoint[]
  alerts: IoTAlert[]
  loading: boolean
}

export const useIoTStore = defineStore('iot', {
  state: (): State => ({ latest: {}, latestByResource: {}, timeline: [], alerts: [], loading: false }),
  getters: {
    latestList: (s) => Object.values(s.latest),
    activeAlerts: (s) => s.alerts.filter((a) => a.status === 'active'),
  },
  actions: {
    /** 写入一条最新数据，并同步按资源索引 */
    _writeLatest(point: IoTDataPoint) {
      this.latest[point.device_code] = point
      const rid = point.resource_id || 0
      if (rid > 0) {
        const prev = this.latestByResource[rid]
        // 同资源多设备时保留时间更新的一条
        if (!prev || prev.recorded_at <= point.recorded_at) {
          this.latestByResource[rid] = point
        }
      }
    },
    async fetchLatest() {
      this.loading = true
      try {
        const { data: resp } = await queryIoTData({ limit: 200 })
        // 接口按时间倒序返回，先写旧再写新，保证最新值覆盖
        resp.data.slice().reverse().forEach((d) => {
          if (d.resource_id === undefined) d.resource_id = 0
          this._writeLatest(d)
        })
        this.timeline = resp.data.slice().reverse()
      } finally {
        this.loading = false
      }
    },
    async fetchAlerts() {
      const { data: resp } = await listAlerts({ status: 'active', limit: 50 })
      this.alerts = resp.alerts
    },
    /** 标记告警已处理，并从活跃列表移除 */
    async resolveAlert(id: number) {
      await apiResolveAlert(id)
      this.onAlertResolved(id)
    },
    /** 其他运营端处理告警后，经 WebSocket 通知本地移除 */
    onAlertResolved(id: number) {
      this.alerts = this.alerts.filter((a) => a.id !== id)
    },
    /** WebSocket iot_data 事件触发 */
    onRealtime(data: any) {
      const point: IoTDataPoint = {
        device_code: data.device_code,
        resource_id: data.resource_id ?? 0,
        temperature: data.temperature,
        humidity: data.humidity,
        longitude: data.longitude,
        latitude: data.latitude,
        recorded_at: data.recorded_at,
      }
      this._writeLatest(point)
      this.timeline.push(point)
      if (this.timeline.length > 500) this.timeline.shift()
    },
  },
})
