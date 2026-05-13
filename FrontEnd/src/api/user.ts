import client from './client'
import type { Review, Comment } from '@/types/review'
import type { Genre } from '@/types/movie'
import type { PaginatedResponse } from '@/types/api'

export interface FilterType {
  type_num: number
  type_name: string
  movie_count: number
}

export interface FilterInterval {
  interval_id: string
  label: string
  movie_count: number
}

export interface FilterPacket {
  types: FilterType[]
  intervals: FilterInterval[]
}

export const userApi = {
  genres: () =>
    client.get<{ items: Genre[] }>('/user/genres'),

  genreStats: () =>
    client.get<{ items: { genre_id: number; name: string; count: number }[] }>('/user/genre-stats'),

  filterPacket: () =>
    client.get<FilterPacket>('/user/filter-packet'),

  reviews: (params: { movie_id: number; page?: number; page_size?: number }) =>
    client.get<PaginatedResponse<Review>>('/user/reviews', { params }),

  comments: (params: { movie_id: number; page?: number; page_size?: number }) =>
    client.get<PaginatedResponse<Comment>>('/user/comments', { params }),
}
