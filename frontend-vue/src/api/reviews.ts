import { http } from './client'

export interface Review {
  id: number
  order_id: number
  from_user_id: number
  to_user_id: number
  rating: number
  content?: string | null
  created_at: string
  from_username?: string | null
}

export interface UserRatingSummary {
  user_id: number
  count: number
  average: number
  credit_score: number
  reviews: Review[]
}

export function createReview(payload: { order_id: number; rating: number; content?: string }) {
  return http.post<Review>('/api/reviews', payload)
}

export function listOrderReviews(orderId: number) {
  return http.get<Review[]>(`/api/reviews/order/${orderId}`)
}

export function getUserRating(userId: number) {
  return http.get<UserRatingSummary>(`/api/reviews/user/${userId}`)
}
