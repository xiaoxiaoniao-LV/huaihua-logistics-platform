import { http } from './client'

/** 结算单：pending → confirmed → paid，未打款前可 void。Decimal 字段按字符串返回。 */
export interface Settlement {
  id: number
  order_id: number
  supplier_id: number
  amount: number | string
  commission_rate: number | string
  commission: number | string
  payable_to_supplier: number | string
  status: 'pending' | 'confirmed' | 'paid' | 'void' | string
  remark?: string | null
  settled_at?: string | null
  created_at: string
}

/** 按日对账汇总。 */
export interface Reconciliation {
  day: string
  orders: number
  gmv: number
  commission: number
  paid_amount: number
  pending_settlements: number
  pending_payout: number
}

export function listSettlements(params?: {
  status?: string
  page?: number
  page_size?: number
}) {
  return http.get<Settlement[]>('/api/v1/settlements', { params })
}

export function getReconciliation(day?: string) {
  return http.get<Reconciliation>('/api/v1/settlements/reconciliation', {
    params: day ? { day } : undefined,
  })
}

export function updateSettlementStatus(id: number, newStatus: string, remark?: string) {
  return http.put<Settlement>(`/api/v1/settlements/${id}/status`, null, {
    params: { new_status: newStatus, ...(remark ? { remark } : {}) },
  })
}

/** 下载结算凭证（单页 A4 发票 PDF）。 */
export function getInvoicePdf(id: number) {
  return http.get<Blob>(`/api/v1/settlements/${id}/invoice.pdf`, { responseType: 'blob' })
}

/** 租户分账：按供给方聚合结算笔数、金额、佣金与已付/待付。 */
export interface SettlementSplitRow {
  supplier_id: number
  supplier_name: string
  settlements: number
  amount: number
  commission: number
  payable: number
  paid: number
  unpaid: number
}

export interface SettlementSplit {
  start: string | null
  end: string | null
  suppliers: number
  items: SettlementSplitRow[]
  total: Omit<SettlementSplitRow, 'supplier_id' | 'supplier_name'>
}

export function getSettlementSplit(params?: { start?: string; end?: string }) {
  return http.get<SettlementSplit>('/api/v1/settlements/split', { params })
}
