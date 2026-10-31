import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useIoTStore } from './iot'
import { useOrdersStore } from './orders'

function point(overrides: Record<string, unknown> = {}) {
  return {
    device_code: 'CW-01',
    resource_id: 1,
    temperature: -18,
    humidity: 60,
    recorded_at: '2026-10-30T10:00:00',
    ...overrides,
  }
}

describe('iot store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('实时数据写入最新值并按资源索引', () => {
    const iot = useIoTStore()
    iot.onRealtime(point())
    expect(iot.latest['CW-01'].temperature).toBe(-18)
    expect(iot.latestByResource[1].device_code).toBe('CW-01')
  })

  it('同资源多设备保留时间更新的一条', () => {
    const iot = useIoTStore()
    iot.onRealtime(point({ device_code: 'CW-01', recorded_at: '2026-10-30T10:00:00' }))
    iot.onRealtime(point({ device_code: 'CW-02', recorded_at: '2026-10-30T10:05:00' }))
    expect(iot.latestByResource[1].device_code).toBe('CW-02')

    // 旧数据不会覆盖新数据
    iot.onRealtime(point({ device_code: 'CW-01', recorded_at: '2026-10-30T10:01:00' }))
    expect(iot.latestByResource[1].device_code).toBe('CW-02')
  })

  it('未绑定资源的设备不进入资源索引', () => {
    const iot = useIoTStore()
    iot.onRealtime(point({ device_code: 'FREE', resource_id: 0 }))
    expect(iot.latest['FREE']).toBeTruthy()
    expect(iot.latestByResource[0]).toBeUndefined()
  })

  it('标记告警已处理后从活跃列表移除', () => {
    const iot = useIoTStore()
    iot.alerts = [
      { id: 1, type: 'temperature_high', level: 'critical', message: 'x', status: 'active', created_at: '' },
      { id: 2, type: 'humidity_high', level: 'warn', message: 'y', status: 'active', created_at: '' },
    ]
    iot.onAlertResolved(1)
    expect(iot.activeAlerts.map((a) => a.id)).toEqual([2])
  })

  it('时间轴超过 500 条时裁剪', () => {
    const iot = useIoTStore()
    for (let i = 0; i < 520; i += 1) iot.onRealtime(point())
    expect(iot.timeline.length).toBe(500)
  })
})

describe('orders store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('订单状态事件只更新已存在的订单', () => {
    const orders = useOrdersStore()
    orders.items = [
      {
        id: 9, resource_id: 1, supplier_id: 1, demander_id: 2,
        total_price: 100, commission_rate: 0.1, status: 'pending', created_at: '',
      },
    ]
    orders.onRealtime({ order_id: 9, new_status: 'confirmed' })
    orders.onRealtime({ order_id: 404, new_status: 'cancelled' })
    expect(orders.items[0].status).toBe('confirmed')
    expect(orders.items.length).toBe(1)
  })
})
