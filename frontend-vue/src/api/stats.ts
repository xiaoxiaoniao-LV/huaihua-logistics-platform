import { http } from './client'

export interface StatsOverview {
  resources: { total: number; by_status: Record<string, number>; available: number; booked: number; pending: number }
  orders: { total: number; by_status: Record<string, number>; finished: number; cancelled: number }
  revenue: { finished_amount: number; commission: number; avg_order_value: number }
  users: { total: number; by_role: Record<string, number> }
  devices: { total: number; online: number; offline: number }
  alerts: { total: number; active: number; resolved: number }
  reviews: { avg_rating: number }
}

export interface TrendPoint {
  date: string
  orders: number
  amount: number
  commission: number
  alerts: number
}

export interface ResourceStat {
  type: string
  name: string
  total: number
  available: number
  booked: number
  pending: number
  offline: number
  finished_amount: number
  utilization: number
}

export function getStatsOverview() {
  return http.get<StatsOverview>('/api/stats/overview')
}

export function getStatsTrend(days = 7) {
  return http.get<{ days: number; items: TrendPoint[] }>('/api/stats/trend', { params: { days } })
}

export function getStatsResources() {
  return http.get<{ items: ResourceStat[] }>('/api/stats/resources')
}
