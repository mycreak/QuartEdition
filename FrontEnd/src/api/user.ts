import client from './client'
import type { Review, Comment } from '@/types/review'
import type { Genre, MovieStatus, PlaylistBrief, PlaylistDetail } from '@/types/movie'
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
  regions: string[]
  years: number[]
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

  /** 片单 — 已发布轮播列表 */
  playlists: () =>
    client.get<{ items: PlaylistBrief[]; total: number }>('/user/playlists'),

  /** 片单详情 */
  playlistDetail: (id: number) =>
    client.get<PlaylistDetail>(`/user/playlists/${id}`),
}

// ── 用户行为评分 ──

export interface ActionResult {
  action: string
  movie_id: number
  score_total: number
  tag_count: number
}

export const userActionApi = {
  /** 查询用户对某电影的标记状态 */
  status: (movieId: number) =>
    client.get<MovieStatus>(`/user/movies/${movieId}/status`),

  /** 标记 / 取消标记 */
  mark: (movieId: number, action: string) =>
    client.post<ActionResult>(`/user/movies/${movieId}/${action}`),

  unmark: (movieId: number, action: string) =>
    client.delete<ActionResult>(`/user/movies/${movieId}/${action}`),

  /** 提交评论 */
  comment: (movieId: number, data: { review_text: string; rating?: number }) =>
    client.post<ActionResult>(`/user/movies/${movieId}/comment`, data),

  /** 删除评论 */
  deleteComment: (movieId: number) =>
    client.delete<ActionResult>(`/user/movies/${movieId}/comment`),

  /** 查询我的电影列表（按行为类型） */
  myMovies: (type_: string, page = 1, pageSize = 20) =>
    client.get<PaginatedResponse<{ movie_id: number; title: string; poster_url?: string; release_year?: number; douban_id?: string; rating?: number; ai_summary?: string }>>('/user/profile/movies', { params: { type: type_, page, page_size: pageSize } }),

  /** 查询我的评论列表 */
  myComments: (page = 1, pageSize = 20) =>
    client.get<PaginatedResponse<{ movie_id: number; title?: string; text: string; rating?: number; date?: string }>>('/user/profile/comments', { params: { page, page_size: pageSize } }),
}
