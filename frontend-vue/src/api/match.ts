import { http } from './client'

export interface ScoreBreakdown {
  price_score: number
  credit_score: number
  window_score: number
  type_match: number
}

export interface MatchResult {
  resource_id: number
  name: string
  type: string
  price: number | null
  price_unit: string | null
  location?: string | null
  status?: string
  match_score: number
  score_breakdown?: ScoreBreakdown
}

export function recommend(params: {
  type?: string
  max_price?: number
  top_n?: number
}) {
  return http.get<{ count: number; results: MatchResult[] }>('/api/match/recommend', { params })
}
