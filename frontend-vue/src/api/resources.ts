import { http } from './client'

export interface Resource {
  id: number
  user_id: number
  type: 'warehouse' | 'cold_box' | 'vehicle' | 'equipment' | string
  name: string
  description?: string | null
  location?: string | null
  params?: Record<string, any> | null
  available_start?: string | null
  available_end?: string | null
  price?: number | null
  price_unit?: string | null
  status: 'pending' | 'available' | 'booked' | 'offline' | string
  created_at: string
}

export function listResources(params?: {
  type?: string
  status?: string
  keyword?: string
  page?: number
  page_size?: number
}) {
  return http.get<Resource[]>('/api/resources', { params })
}

export function getResource(id: number) {
  return http.get<Resource>(`/api/resources/${id}`)
}

export interface ResourcePayload {
  type: string
  name: string
  description?: string | null
  location?: string | null
  price?: number | string | null
  price_unit?: string | null
  available_start?: string | null
  available_end?: string | null
}

export function createResource(payload: ResourcePayload) {
  return http.post<Resource>('/api/resources', payload)
}

export function updateResource(id: number, payload: Partial<ResourcePayload> & { status?: string }) {
  return http.put<Resource>(`/api/resources/${id}`, payload)
}

export function deleteResource(id: number) {
  return http.delete<void>(`/api/resources/${id}`)
}

/** 管理员审核待审核资源：通过→上架，驳回→下架 */
export function reviewResource(id: number, approve: boolean, reason?: string) {
  return http.post<Resource>(`/api/resources/${id}/review`, { approve, reason })
}
