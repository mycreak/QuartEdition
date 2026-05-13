import client from '@/api/client'
import type { Movie, MovieDetail } from '@/types/movie'
import type { PaginatedResponse } from '@/types/api'
import type { MovieWithPendingReviews, PendingReview } from '@/types/task'

export const adminMoviesApi = {
  list: (params: { keyword?: string; type_num?: number; published?: number; page?: number; page_size?: number }) =>
    client.get<PaginatedResponse<Movie>>('/admin/movies', { params }),

  detail: (id: number) =>
    client.get<MovieDetail>(`/admin/movies/${id}`),

  publish: (id: number) =>
    client.post<{ success: boolean; message: string }>(`/admin/movies/${id}/publish`),

  unpublish: (id: number) =>
    client.post<{ success: boolean; message: string }>(`/admin/movies/${id}/unpublish`),

  update: (id: number, data: { title?: string; douban_id?: string; release_year?: number; poster_url?: string }) =>
    client.patch<{ success: boolean; movie: Movie }>(`/admin/movies/${id}`, data),

  addCredit: (movieId: number, data: { person_id: number; role_type: string }) =>
    client.post<{ success: boolean; affected: number }>(`/admin/movies/${movieId}/credits`, data),

  removeCredit: (movieId: number, data: { person_id: number; role_type: string }) =>
    client.delete<{ success: boolean; affected: number }>(`/admin/movies/${movieId}/credits`, { data }),

  addGenre: (movieId: number, data: { type_num: number }) =>
    client.post<{ success: boolean; affected: number }>(`/admin/movies/${movieId}/genres`, data),

  removeGenre: (movieId: number, typeNum: number) =>
    client.delete<{ success: boolean; affected: number }>(`/admin/movies/${movieId}/genres/${typeNum}`),

  addRegion: (movieId: number, data: { region_id: number }) =>
    client.post<{ success: boolean; affected: number }>(`/admin/movies/${movieId}/regions`, data),

  removeRegion: (movieId: number, regionId: number) =>
    client.delete<{ success: boolean; affected: number }>(`/admin/movies/${movieId}/regions/${regionId}`),

  updateRating: (movieId: number, data: { average: number; count: number }) =>
    client.put<{ success: boolean; average: number; count: number }>(`/admin/movies/${movieId}/rating`, data),

  getMoviesWithPendingReviews: () =>
    client.get<{ items: MovieWithPendingReviews[] }>('/admin/movies/with-pending-reviews'),

  getPendingReviews: (movieId: number, params: { page?: number; page_size?: number }) =>
    client.get<{ items: PendingReview[]; total: number; page: number; page_size: number }>(
      `/admin/movies/${movieId}/pending-reviews`,
      { params }
    ),
}
