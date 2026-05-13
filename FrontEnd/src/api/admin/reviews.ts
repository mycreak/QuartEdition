import client from '@/api/client'
import type { PaginatedResponse } from '@/types/api'

export interface AdminReview {
  review_id: string
  movie_id: number
  movie_title?: string
  author: string
  text: string
  rating?: number
  is_published: boolean
  created_at: string
}

export interface AdminComment {
  comment_id: string
  movie_id: number
  movie_title?: string
  author: string
  text: string
  rating?: number
  is_published: boolean
  created_at: string
}

export const adminReviewsApi = {
  reviews: (params: { movie_id?: number; page?: number; page_size?: number }) =>
    client.get<PaginatedResponse<AdminReview>>('/admin/reviews', { params }),

  publishReview: (id: string) =>
    client.post<{ success: boolean; message: string }>(`/admin/reviews/${id}/publish`),

  unpublishReview: (id: string) =>
    client.post<{ success: boolean; message: string }>(`/admin/reviews/${id}/unpublish`),

  comments: (params: { movie_id?: number; page?: number; page_size?: number }) =>
    client.get<PaginatedResponse<AdminComment>>('/admin/comments', { params }),

  publishComment: (id: string) =>
    client.post<{ success: boolean; message: string }>(`/admin/comments/${id}/publish`),

  unpublishComment: (id: string) =>
    client.post<{ success: boolean; message: string }>(`/admin/comments/${id}/unpublish`),
}
