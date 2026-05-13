import client from './client'
import type { Movie, MovieDetail, WordCloudItem } from '@/types/movie'
import type { PaginatedResponse } from '@/types/api'

export const moviesApi = {
  list: (params: {
    keyword?: string
    type_num?: number
    interval_ids?: string
    page?: number
    page_size?: number
  }) =>
    client.get<PaginatedResponse<Movie>>('/user/movies', { params }),

  detail: (id: number) =>
    client.get<MovieDetail>(`/user/movies/${id}`),

  getWordCloud: (movieId: number) =>
    client.get<{
      success: boolean
      data: {
        words: WordCloudItem[]
        total_words: number
        updated_at: string | null
      }
    }>(`/user/movies/${movieId}/comment-wordcloud`),
}

