import { idempotencyKey, query, request } from './http'

export interface Order {
  id: number
  resource_id: number
  supplier_id: number
  demander_id: number
  start_time: string
  end_time: string
  total_price: string | number
  status: string
  payment_status: string
  created_at: string
}

export const orderStatusLabels: Record<string, string> = {
  pending: '待供给方确认',
  confirmed: '已确认',
  ongoing: '履约中',
  finished: '已完成',
  settled: '已结算',
  rejected: '已拒绝',
  cancelled: '已取消',
  expired: '已超时关闭',
}

export const orderStatusTags: Record<string, string> = {
  pending: 'tag-orange',
  confirmed: 'tag-blue',
  ongoing: 'tag-blue',
  finished: 'tag-green',
  settled: 'tag-green',
  rejected: 'tag-red',
  cancelled: 'tag-grey',
  expired: 'tag-grey',
}

export function createOrder(payload: { resource_id: number; start_time: string; end_time: string }) {
  return request<Order>({
    url: '/api/v1/orders',
    method: 'POST',
    data: payload,
    header: { 'Idempotency-Key': idempotencyKey() },
  })
}

export function listMyOrders() {
  return request<Order[]>({ url: `/api/v1/orders${query({ mine: 'demander', page_size: 100 })}` })
}

export function cancelOrder(orderId: number) {
  return request<Order>({
    url: `/api/v1/orders/${orderId}/status${query({ new_status: 'cancelled', reason: '需求方取消' })}`,
    method: 'PUT',
  })
}
