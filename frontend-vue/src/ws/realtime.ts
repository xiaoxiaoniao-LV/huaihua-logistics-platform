/**
 * WebSocket 实时通道封装（单例）。
 * 后端：ws://host:8002/ws/realtime（无鉴权，欢迎包 + BroadcastHub 订阅）。
 * 前端：自动重连 + 心跳 + 类型化事件分发。
 */

type Listener = (data: any) => void

interface WSMessage {
  type: string
  [k: string]: any
}

class Realtime {
  private ws: WebSocket | null = null
  private url: string
  private listeners = new Map<string, Set<Listener>>()
  private reconnectDelay = 1000
  private maxReconnectDelay = 30000
  private heartbeatTimer: number | null = null
  private reconnectTimer: number | null = null
  private manuallyClosed = false

  constructor(url: string) {
    this.url = url
  }

  connect() {
    this.manuallyClosed = false
    this._connect()
  }

  private _connect() {
    try {
      this.ws = new WebSocket(this.url)
    } catch (e) {
      console.error('[WS] 创建连接失败:', e)
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      console.log('[WS] 已连接')
      this.reconnectDelay = 1000
      this._startHeartbeat()
    }

    this.ws.onmessage = (ev) => {
      let msg: WSMessage
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return
      }
      this._dispatch(msg)
    }

    this.ws.onclose = () => {
      console.warn('[WS] 连接关闭')
      this._stopHeartbeat()
      if (!this.manuallyClosed) this._scheduleReconnect()
    }

    this.ws.onerror = (ev) => {
      console.error('[WS] 错误:', ev)
    }
  }

  private _scheduleReconnect() {
    if (this.reconnectTimer) return
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null
      this._connect()
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay)
    }, this.reconnectDelay)
  }

  private _startHeartbeat() {
    this._stopHeartbeat()
    this.heartbeatTimer = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping', at: Date.now() }))
      }
    }, 30000)
  }

  private _stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  close() {
    this.manuallyClosed = true
    this._stopHeartbeat()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
    this.ws = null
  }

  /** 订阅事件（按 type 分发）。all 可监听所有消息。 */
  on(type: string, fn: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set())
    this.listeners.get(type)!.add(fn)
  }

  off(type: string, fn: Listener) {
    this.listeners.get(type)?.delete(fn)
  }

  private _dispatch(msg: WSMessage) {
    // 广播到 all
    this.listeners.get('all')?.forEach((fn) => fn(msg))
    // 广播到具体 type
    if (msg.type) {
      this.listeners.get(msg.type)?.forEach((fn) => fn(msg))
    }
  }
}

// 未显式配置时走同源；HTTPS 页面自动使用 wss
const WS_PROTO = location.protocol === 'https:' ? 'wss' : 'ws'
const URL = (import.meta.env.VITE_WS_URL as string) || `${WS_PROTO}://${location.host}/ws/realtime`
export const realtime = new Realtime(URL)
