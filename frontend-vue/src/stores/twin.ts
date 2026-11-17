/** 数字孪生大屏状态：一次性快照 + 四级下钻 + 设备点位实时面板。 */
import { defineStore } from 'pinia'
import {
  fetchDeviceEvents, fetchDeviceState, fetchTwinSnapshot,
  type DeviceState, type TwinEventRow, type TwinNode, type TwinSnapshot,
} from '@/api/twin'

const STATUS_RANK: Record<string, number> = {
  online: 0, unknown: 1, offline: 2, degraded: 3, alarm: 4, maintenance: 5,
}

export const NODE_TYPE_LABEL: Record<string, string> = {
  site: '园区', zone: '库区', building: '库房', floor: '楼层',
  room: '库房', rack: '货架', device: '设备',
}

interface State {
  snapshot: TwinSnapshot | null
  path: TwinNode[]
  selectedDevice: string | null
  deviceDetail: DeviceState | null
  deviceEvents: TwinEventRow[]
  loading: boolean
  error: string
  updatedAt: string
}

export const useTwinStore = defineStore('twin', {
  state: (): State => ({
    snapshot: null,
    path: [],
    selectedDevice: null,
    deviceDetail: null,
    deviceEvents: [],
    loading: false,
    error: '',
    updatedAt: '',
  }),
  getters: {
    hasTree: (s) => (s.snapshot?.count || 0) > 0,
    currentNodes: (s): TwinNode[] => {
      if (!s.snapshot) return []
      if (!s.path.length) return s.snapshot.tree
      return s.path[s.path.length - 1]?.children || []
    },
    breadcrumb: (s): TwinNode[] => s.path,
    level: (s) => s.path.length + 1,
    summary: (s): Record<string, number> => s.snapshot?.summary || {},
    devices: (s) => s.snapshot?.devices.items || [],
    alerts: (s) => s.snapshot?.alerts.items || [],
    events: (s) => s.snapshot?.events.items || [],
    /** 设备编码 → 挂在哪些节点上（用于设备面板回显位置） */
    deviceNodes: (s): Record<string, string[]> => {
      const map: Record<string, string[]> = {}
      s.snapshot?.flat.forEach((node) => {
        node.bindings.forEach((b) => {
          const list = map[b.device_code] || (map[b.device_code] = [])
          if (!list.includes(node.name)) list.push(node.name)
        })
      })
      return map
    },
  },
  actions: {
    async fetchSnapshot() {
      this.loading = true
      try {
        const { data } = await fetchTwinSnapshot()
        this.snapshot = data
        this.updatedAt = data.generated_at
        this.error = ''
        this._rebasePath()
      } catch (e: any) {
        this.error = e?.message || '孪生数据加载失败'
      } finally {
        this.loading = false
      }
    },

    /** 快照刷新后按 node_key 重新指向新对象，避免 path 里持有旧快照 */
    _rebasePath() {
      if (!this.path.length || !this.snapshot) return
      const flat = new Map(this.snapshot.flat.map((n) => [n.node_key, n]))
      const next: TwinNode[] = []
      let cursor: TwinNode[] = this.snapshot.tree
      for (const old of this.path) {
        const hit = cursor.find((n) => n.node_key === old.node_key)
        if (!hit) break
        next.push(hit)
        cursor = hit.children
        if (!flat.has(hit.node_key)) break
      }
      this.path = next
    },

    drill(node: TwinNode) {
      this.path = [...this.path, node]
    },

    upTo(index: number) {
      this.path = this.path.slice(0, Math.max(0, index))
    },

    reset() {
      this.path = []
      this.selectedDevice = null
      this.deviceDetail = null
      this.deviceEvents = []
    },

    async selectDevice(code: string | null) {
      this.selectedDevice = code
      if (!code) {
        this.deviceDetail = null
        this.deviceEvents = []
        return
      }
      try {
        const [state, events] = await Promise.all([
          fetchDeviceState(code),
          fetchDeviceEvents(code, 12),
        ])
        this.deviceDetail = state.data
        this.deviceEvents = events.data.events
      } catch {
        this.deviceDetail = null
        this.deviceEvents = []
      }
    },

    /** WebSocket telemetry：更新设备行与绑定点位值，再重算节点状态 */
    onTelemetry(msg: any) {
      if (!this.snapshot || !msg?.device_code) return
      const code = msg.device_code as string
      const row = this.snapshot.devices.items.find((d) => d.device_code === code)
      if (row) {
        row.status = msg.status ?? row.status
        row.quality = msg.quality ?? row.quality
        row.last_seen_at = msg.last_seen_at ?? row.last_seen_at
        row.age_ms = 0
        if (msg.points) row.point_count = Math.max(row.point_count, Object.keys(msg.points).length)
      }

      this._walk((node) => {
        node.bindings.forEach((b) => {
          if (b.device_code !== code) return
          b.device_status = msg.status ?? b.device_status
          const p = msg.points?.[b.point_key]
          if (p) {
            b.value = p.value_num ?? p.value_text ?? null
            b.quality = msg.quality ?? b.quality
            b.ts = msg.last_seen_at ?? b.ts
          }
        })
      })
      if (this.deviceDetail?.device_code === code) {
        this.deviceDetail.status = msg.status ?? this.deviceDetail.status
        this.deviceDetail.quality = msg.quality ?? this.deviceDetail.quality
        this.deviceDetail.last_seen_at = msg.last_seen_at ?? this.deviceDetail.last_seen_at
        this.deviceDetail.age_ms = 0
        this.deviceDetail.points.forEach((pt) => {
          const p = msg.points?.[pt.point_key]
          if (!p) return
          pt.value = p.value_num ?? p.value_text ?? null
          pt.quality = msg.quality ?? pt.quality
          pt.ts = msg.last_seen_at ?? pt.ts
          pt.age_ms = 0
        })
      }
      this._recomputeStatuses()
    },

    /** 门磁/告警事件：只更新计数与事件流，状态由下一次遥测或轮询校正 */
    onTwinEvent(msg: any) {
      if (!this.snapshot) return
      this.snapshot.events.items.unshift({
        id: Date.now(),
        device_code: msg.device_code ?? null,
        event_type: msg.kind === 'door' ? (msg.open ? 'door_open' : 'door_close') : (msg.kind || 'event'),
        severity: msg.level === 'critical' ? 'critical' : 'warn',
        message: msg.message ?? null,
        ts: new Date().toISOString(),
        resolved_at: null,
      })
      this.snapshot.events.items = this.snapshot.events.items.slice(0, 20)
      this.snapshot.events.count = this.snapshot.events.items.length
    },

    /** 深度遍历节点树（更新绑定值 / 重算状态 / 统计都基于同一份对象） */
    _walk(fn: (node: TwinNode) => void) {
      const visit = (node: TwinNode) => {
        fn(node)
        node.children.forEach(visit)
      }
      this.snapshot?.tree.forEach(visit)
    },

    _recomputeStatuses() {
      if (!this.snapshot) return

      const ownStatus = (node: TwinNode): string => {
        if (!node.bindings.length) return 'unknown'
        let worst = 'online'
        for (const b of node.bindings) {
          let state = b.device_status || 'unknown'
          if (state === 'online' && (b.quality === 'stale' || b.quality === 'bad')) state = 'degraded'
          if (STATUS_RANK[state] > STATUS_RANK[worst]) worst = state
        }
        return worst
      }

      const resolve = (node: TwinNode): string => {
        const states = [ownStatus(node), ...node.children.map(resolve)]
        let worst = 'unknown'
        for (const s of states) {
          if (s === 'unknown' && worst === 'unknown') continue
          if (STATUS_RANK[s] > STATUS_RANK[worst]) worst = s
        }
        node.status = worst
        return worst
      }
      this.snapshot.tree.forEach(resolve)

      const summary: Record<string, number> = {}
      this._walk((n) => {
        summary[n.status] = (summary[n.status] || 0) + 1
      })
      this.snapshot.summary = summary
    },
  },
})
