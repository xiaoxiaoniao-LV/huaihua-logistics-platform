import { http } from './client'

export interface Order {
  id: number
  resource_id: number
  supplier_id: number
  demander_id: number
  start_time?: string | null
  end_time?: string | null
  total_price?: number | null
  commission_rate?: number
  commission?: number | null
  status:
    | 'inquiry'
    | 'pending'
    | 'confirmed'
    | 'ongoing'
    | 'finished'
    | 'settled'
    | 'rejected'
    | 'cancelled'
    | 'expired'
    | string
  payment_status?: 'unpaid' | 'paid' | 'refunding' | 'refunded' | 'waived' | string
  cancel_reason?: string | null
  version?: number
  created_at: string
  updated_at?: string | null
}

export function listOrders(params?: { mine?: 'demander' | 'supplier'; page?: number; page_size?: number }) {
  return http.get<Order[]>('/api/v1/orders', { params })
}

export function createOrder(payload: { resource_id: number; start_time: string; end_time: string }) {
  return http.post<Order>('/api/v1/orders', payload)
}

export function updateOrderStatus(id: number, status: string) {
  // 后端接口参数名为 new_status（Query）
  return http.put<Order>(`/api/v1/orders/${id}/status`, null, { params: { new_status: status } })
}
