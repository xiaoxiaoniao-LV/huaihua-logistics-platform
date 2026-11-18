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
  room: '库房', rack: '货架', slot: '货位', device: '设备',
}

interface State {
  snapshot: TwinSnapshot | null
  path: TwinNode[]
  selectedDevice: string | null
  deviceDetail: DeviceState | null
  deviceEvents: TwinEventRow[]
  /** 左右栏联动：需要 3D 聚焦的节点 / 资源 */
  highlightKey: string | null
  focusResourceId: number | null
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
    highlightKey: null,
    focusResourceId: null,
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
      const last = this.path[this.path.length - 1]
      const next = this._pathTo(last.node_key)
      if (next.length) this.path = next
    },

    /** 从根节点到目标节点的完整祖先链（园区 → 库房 → 货位 → 设备） */
    _pathTo(nodeKey: string): TwinNode[] {
      if (!this.snapshot) return []
      const dfs = (nodes: TwinNode[], trail: TwinNode[]): TwinNode[] | null => {
        for (const node of nodes) {
          const next = [...trail, node]
          if (node.node_key === nodeKey) return next
          const hit = dfs(node.children, next)
          if (hit) return hit
        }
        return null
      }
      return dfs(this.snapshot.tree, []) || []
    },

    drill(node: TwinNode) {
      const trail = this._pathTo(node.node_key)
      this.path = trail.length ? trail : [...this.path, node]
    },

    upTo(index: number) {
      this.path = this.path.slice(0, Math.max(0, index))
    },

    reset() {
      this.path = []
      this.selectedDevice = null
      this.deviceDetail = null
      this.deviceEvents = []
      this.highlightKey = null
      this.focusResourceId = null
    },

    /** 左栏资源点击：定位到该资源所在的货位并聚焦 */
    focusResource(resourceId: number) {
      this.focusResourceId = resourceId
      if (!this.snapshot) return
      const slot = this.snapshot.flat.find(
        (n) => n.node_type === 'slot' && Number((n.transform as any)?.resource_id) === resourceId,
      )
      if (slot) this._focusSlot(slot)
    },

    /** 三维场景点选货位：与资源列表点击走同一路径（停在库房层，高亮货位 + 带出设备） */
    focusSlot(node: TwinNode) {
      this.focusResourceId = Number((node.transform as any)?.resource_id) || null
      this._focusSlot(node)
    },

    _focusSlot(slot: Omit<TwinNode, 'children'>) {
      if (!this.snapshot) return
      const trail = this._pathTo(slot.node_key)
      if (trail.length < 2) return
      this.path = trail.slice(0, -1)
      this.highlightKey = slot.node_key
      const device = this.snapshot.flat.find(
        (n) => n.parent_id === slot.id && n.node_type === 'device',
      )
      this.selectDevice(device?.bindings[0]?.device_code ?? null)
    },

    /** 右栏告警点击：定位到该设备所属货位 */
    focusDevice(code: string) {
      if (!this.snapshot) return
      const device = this.snapshot.flat.find(
        (n) => n.node_type === 'device' && n.bindings.some((b) => b.device_code === code),
      )
      if (!device) return
      const slot = this.snapshot.flat.find((n) => n.id === device.parent_id)
      if (slot) {
        const trail = this._pathTo(slot.node_key)
        if (trail.length >= 2) {
          this.path = trail.slice(0, -1)
          this.highlightKey = slot.node_key
        }
      }
      this.selectDevice(code)
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

      // unknown 不参与「最坏值」比较：全为 unknown 时才回落为 unknown
      const resolve = (node: TwinNode): string => {
        let worst: string | null = null
        for (const s of [ownStatus(node), ...node.children.map(resolve)]) {
          if (s === 'unknown') continue
          if (worst === null || STATUS_RANK[s] > STATUS_RANK[worst]) worst = s
        }
        node.status = worst ?? 'unknown'
        return node.status
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
