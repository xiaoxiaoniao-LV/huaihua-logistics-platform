import { query, request } from './http'

export type ResourceType = 'warehouse' | 'cold_box' | 'vehicle' | 'equipment'

export const typeLabels: Record<string, string> = {
  warehouse: '冷库',
  cold_box: '冷链箱位',
  vehicle: '冷藏运输',
  equipment: '温控设备',
}

export interface Resource {
  id: number
  user_id: number
  type: string
  name: string
  location: string | null
  price: string | number | null
  price_unit: string | null
  status: string
  description: string | null
  available_start: string | null
  available_end: string | null
}

export interface MatchItem {
  resource_id: number
  name: string
  type: string
  price: number | null
  price_unit: string | null
  location: string | null
  status: string
  match_score: number
  reasons: string[]
}

export function formatPrice(
  price: string | number | null | undefined,
  unit: string | null | undefined,
) {
  if (price === null || price === undefined || price === '') return '价格面议'
  const u = (unit || '天').replace(/^元\s*\/?\s*/, '')
  return `¥${price}/${u}`
}

export function listResources(params: {
  keyword?: string
  type?: string
  page?: number
  page_size?: number
}) {
  return request<Resource[]>({
    url: `/api/v1/resources${query({ status: 'available', ...params })}`,
  })
}

export function getResource(id: number, silent = false) {
  return request<Resource>({ url: `/api/v1/resources/${id}`, silent })
}

export function recommendResources(params: { type?: string; top_n?: number } = {}) {
  return request<{ count: number; results: MatchItem[] }>({
    url: `/api/v1/match/recommend${query({ top_n: 3, ...params })}`,
  })
}
