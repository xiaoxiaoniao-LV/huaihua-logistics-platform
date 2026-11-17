import { http } from './client'

/** 支付意图：sandbox 模式返回本机模拟收银台 pay_url。 */
export interface PaymentIntent {
  already_paid: boolean
  order_id: number
  provider?: string
  trade_no?: string
  amount?: number
  pay_url?: string
}

export function createPaymentIntent(orderId: number) {
  return http.post<PaymentIntent>(`/api/v1/payments/${orderId}/intent`)
}
