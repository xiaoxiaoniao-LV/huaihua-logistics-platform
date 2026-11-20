import { request } from './http'

export interface PaymentIntent {
  already_paid: boolean
  order_id: number
  provider?: string
  trade_no?: string
  amount?: number
  /** 收银台地址（sandbox 模式为本机模拟收银台） */
  pay_url?: string
}

export function createPaymentIntent(orderId: number) {
  return request<PaymentIntent>({
    url: `/api/v1/payments/${orderId}/intent`,
    method: 'POST',
  })
}

/** sandbox 模拟收银台：请求即视为支付成功（仅演示环境可用）。 */
export function mockCheckout(payUrl: string) {
  return request<{ order_id: number; payment_status: string; trade_no: string }>({
    url: payUrl,
  })
}
